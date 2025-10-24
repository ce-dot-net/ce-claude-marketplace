# Semantic De-duplication - Implementation Specification

**Status**: Ready for implementation
**Target**: Reach 98% paper compliance
**Effort**: 3-4 days
**Components**: Server (primary), MCP Client (activation only)

---

## 📋 Overview

### Current Implementation
```python
# Exact string matching only
def is_duplicate(new_bullet: str, existing: List[str]) -> bool:
    return new_bullet in existing  # Exact match
```

**Problem**: Semantically equivalent bullets with different wording are not caught:
- "Use JWT tokens for authentication"
- "Implement JSON Web Tokens for auth"
- "Add JWT-based authentication system"

### Target Implementation
```python
# Semantic similarity with 85% threshold
async def is_duplicate(new_bullet: str, existing: List[PlaybookBullet]) -> bool:
    new_embedding = await get_embedding(new_bullet)

    for bullet in existing:
        existing_embedding = await get_embedding(bullet.content)
        similarity = cosine_similarity(new_embedding, existing_embedding)

        if similarity >= 0.85:  # Paper's threshold
            return True

    return False
```

**Benefit**: Prevents playbook bloat by detecting semantic duplicates regardless of wording.

---

## 🏗️ Architecture

### Component Responsibilities

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Server (Curator) - Main Logic                          │
│    - Generate embeddings for bullets                       │
│    - Compare semantic similarity                           │
│    - Mark duplicates, prevent addition                     │
└─────────────────────────────────────────────────────────────┘
                    ↓ uses
┌─────────────────────────────────────────────────────────────┐
│ 2. Server (Embedding Service) - New Component             │
│    - Interface to embedding API                            │
│    - Caching layer (Redis/in-memory)                       │
│    - Batch processing for efficiency                       │
└─────────────────────────────────────────────────────────────┘
                    ↓ caches in
┌─────────────────────────────────────────────────────────────┐
│ 3. MCP Client (Local Cache) - Already Exists!             │
│    - SQLite-based embedding cache                          │
│    - Methods already implemented                           │
│    - Just needs server to use it                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Server-Side Implementation

### 1. Create Embedding Service

**File**: `server/ace_server/services/embedding_service.py` (NEW)

```python
"""
Embedding service for semantic similarity comparison.
Uses OpenAI's text-embedding-3-small model.
"""

from typing import List, Optional
import numpy as np
from openai import AsyncOpenAI
import hashlib
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Manages embedding generation with caching.

    Cost optimization:
    - Caches embeddings in memory (session)
    - Delegates to MCP client for persistent cache (SQLite)
    - Batches requests when possible
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        cache_enabled: bool = True
    ):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.cache_enabled = cache_enabled

        # In-memory cache (session-scoped)
        self._cache: dict[str, np.ndarray] = {}

        logger.info(
            f"EmbeddingService initialized with model={model}, "
            f"cache_enabled={cache_enabled}"
        )

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text content."""
        return hashlib.sha256(text.encode()).hexdigest()

    async def get_embedding(self, text: str) -> np.ndarray:
        """
        Get embedding for text with caching.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as numpy array
        """
        if not text.strip():
            raise ValueError("Cannot generate embedding for empty text")

        # Check in-memory cache first
        cache_key = self._get_cache_key(text)
        if self.cache_enabled and cache_key in self._cache:
            logger.debug(f"Embedding cache hit for text: {text[:50]}...")
            return self._cache[cache_key]

        # Generate embedding via API
        logger.debug(f"Generating embedding for text: {text[:50]}...")
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                encoding_format="float"
            )

            embedding = np.array(response.data[0].embedding)

            # Cache the result
            if self.cache_enabled:
                self._cache[cache_key] = embedding

            logger.debug(f"Generated embedding with dimension: {len(embedding)}")
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def get_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Get embeddings for multiple texts in a batch.
        More efficient than individual requests.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Check cache for each text
        results = []
        uncached_indices = []
        uncached_texts = []

        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)
            if self.cache_enabled and cache_key in self._cache:
                results.append((i, self._cache[cache_key]))
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Batch request for uncached texts
        if uncached_texts:
            logger.debug(f"Batch generating {len(uncached_texts)} embeddings")
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=uncached_texts,
                    encoding_format="float"
                )

                for i, data in enumerate(response.data):
                    embedding = np.array(data.embedding)
                    original_index = uncached_indices[i]

                    # Cache the result
                    if self.cache_enabled:
                        cache_key = self._get_cache_key(uncached_texts[i])
                        self._cache[cache_key] = embedding

                    results.append((original_index, embedding))

            except Exception as e:
                logger.error(f"Failed to generate batch embeddings: {e}")
                raise

        # Sort by original index and return
        results.sort(key=lambda x: x[0])
        return [embedding for _, embedding in results]

    def cosine_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Similarity score between 0 and 1
        """
        # Normalize vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Compute cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

        # Clamp to [0, 1] range (should be already, but just in case)
        return float(max(0.0, min(1.0, similarity)))

    def clear_cache(self):
        """Clear in-memory embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_enabled": self.cache_enabled,
            "model": self.model
        }
```

### 2. Update Curator with Semantic Deduplication

**File**: `server/ace_server/curator.py` (MODIFY)

```python
from typing import List, Optional
from .services.embedding_service import EmbeddingService
from .types import PlaybookBullet, DeltaOperation, BulletSection
import logging

logger = logging.getLogger(__name__)


class Curator:
    """
    Curator manages playbook updates with semantic de-duplication.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        semantic_dedup_enabled: bool = True,
        similarity_threshold: float = 0.85
    ):
        self.embedding_service = embedding_service
        self.semantic_dedup_enabled = semantic_dedup_enabled
        self.similarity_threshold = similarity_threshold

        logger.info(
            f"Curator initialized with semantic_dedup={semantic_dedup_enabled}, "
            f"threshold={similarity_threshold}"
        )

    async def apply_deltas(
        self,
        current_playbook: dict[BulletSection, List[PlaybookBullet]],
        deltas: List[DeltaOperation]
    ) -> dict[BulletSection, List[PlaybookBullet]]:
        """
        Apply delta operations with semantic de-duplication.

        Args:
            current_playbook: Current playbook state
            deltas: Delta operations from Reflector

        Returns:
            Updated playbook
        """
        updated_playbook = current_playbook.copy()

        for delta in deltas:
            if delta.type == "ADD":
                # Check for semantic duplicates before adding
                if await self._is_semantic_duplicate(
                    delta.content,
                    delta.section,
                    updated_playbook
                ):
                    logger.info(
                        f"Skipping duplicate bullet (similarity >= {self.similarity_threshold}): "
                        f"{delta.content[:80]}..."
                    )
                    continue

                # Not a duplicate, add to playbook
                new_bullet = PlaybookBullet(
                    id=delta.bullet_id,
                    section=delta.section,
                    content=delta.content,
                    helpful=0,
                    harmful=0,
                    confidence=0.5,  # Initial confidence
                    observations=0,
                    evidence=[],
                    created_at=self._now(),
                    last_used=self._now()
                )

                updated_playbook[delta.section].append(new_bullet)
                logger.info(f"Added new bullet to {delta.section}: {delta.content[:80]}...")

            elif delta.type == "UPDATE":
                # Find bullet by ID and update
                for section_bullets in updated_playbook.values():
                    for bullet in section_bullets:
                        if bullet.id == delta.bullet_id:
                            # Update counters
                            if delta.helpful_delta:
                                bullet.helpful += delta.helpful_delta
                            if delta.harmful_delta:
                                bullet.harmful += delta.harmful_delta

                            # Recalculate confidence
                            total = bullet.helpful + bullet.harmful
                            bullet.confidence = bullet.helpful / total if total > 0 else 0.5

                            bullet.observations += 1
                            bullet.last_used = self._now()

                            logger.debug(f"Updated bullet {bullet.id}: confidence={bullet.confidence:.2f}")
                            break

            elif delta.type == "DELETE":
                # Remove bullet by ID
                for section_bullets in updated_playbook.values():
                    updated_playbook[delta.section] = [
                        b for b in section_bullets if b.id != delta.bullet_id
                    ]
                logger.info(f"Deleted bullet {delta.bullet_id}")

        return updated_playbook

    async def _is_semantic_duplicate(
        self,
        new_content: str,
        section: BulletSection,
        playbook: dict[BulletSection, List[PlaybookBullet]]
    ) -> bool:
        """
        Check if new content is semantically duplicate of existing bullets.

        Args:
            new_content: New bullet content
            section: Playbook section to check
            playbook: Current playbook state

        Returns:
            True if semantic duplicate found
        """
        # Skip if semantic dedup is disabled
        if not self.semantic_dedup_enabled:
            return self._is_exact_duplicate(new_content, section, playbook)

        # Get embeddings for new content
        try:
            new_embedding = await self.embedding_service.get_embedding(new_content)
        except Exception as e:
            logger.error(f"Failed to get embedding for new content, falling back to exact match: {e}")
            return self._is_exact_duplicate(new_content, section, playbook)

        # Check against existing bullets in the same section
        existing_bullets = playbook.get(section, [])

        if not existing_bullets:
            return False

        # Batch get embeddings for existing bullets (more efficient)
        existing_contents = [b.content for b in existing_bullets]

        try:
            existing_embeddings = await self.embedding_service.get_embeddings_batch(
                existing_contents
            )

            # Compare with each existing bullet
            for i, existing_embedding in enumerate(existing_embeddings):
                similarity = self.embedding_service.cosine_similarity(
                    new_embedding,
                    existing_embedding
                )

                if similarity >= self.similarity_threshold:
                    logger.info(
                        f"Semantic duplicate found (similarity={similarity:.2f}): "
                        f"\n  New: {new_content[:80]}..."
                        f"\n  Existing: {existing_contents[i][:80]}..."
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to compare embeddings, falling back to exact match: {e}")
            return self._is_exact_duplicate(new_content, section, playbook)

    def _is_exact_duplicate(
        self,
        new_content: str,
        section: BulletSection,
        playbook: dict[BulletSection, List[PlaybookBullet]]
    ) -> bool:
        """Fallback: exact string matching."""
        existing_bullets = playbook.get(section, [])
        return any(b.content == new_content for b in existing_bullets)

    def _now(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime
        return datetime.utcnow().isoformat()
```

### 3. Configuration

**File**: `server/config.py` (MODIFY)

```python
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Server configuration with semantic de-duplication support."""

    # ... existing settings ...

    # Semantic de-duplication settings
    semantic_dedup_enabled: bool = Field(
        default=True,
        description="Enable semantic de-duplication using embeddings"
    )

    semantic_similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for duplicate detection (0-1)"
    )

    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model to use"
    )

    embedding_cache_enabled: bool = Field(
        default=True,
        description="Enable in-memory embedding cache"
    )

    # OpenAI API settings
    openai_api_key: str = Field(
        ...,
        description="OpenAI API key for embeddings"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
```

### 4. Wire Up in Main Application

**File**: `server/main.py` (MODIFY)

```python
from fastapi import FastAPI
from .services.embedding_service import EmbeddingService
from .curator import Curator
from .config import settings
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="ACE Server")


# Initialize services on startup
@app.on_event("startup")
async def startup():
    """Initialize services with semantic de-duplication."""

    # Create embedding service
    embedding_service = EmbeddingService(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        cache_enabled=settings.embedding_cache_enabled
    )

    # Create curator with semantic dedup
    curator = Curator(
        embedding_service=embedding_service,
        semantic_dedup_enabled=settings.semantic_dedup_enabled,
        similarity_threshold=settings.semantic_similarity_threshold
    )

    # Store in app state
    app.state.embedding_service = embedding_service
    app.state.curator = curator

    logger.info(
        f"ACE Server started with semantic_dedup={settings.semantic_dedup_enabled}, "
        f"threshold={settings.semantic_similarity_threshold}"
    )


@app.get("/health")
async def health():
    """Health check with cache stats."""
    return {
        "status": "healthy",
        "semantic_dedup_enabled": settings.semantic_dedup_enabled,
        "embedding_cache": app.state.embedding_service.get_cache_stats()
    }
```

---

## 📦 Dependencies

### Server Requirements

**File**: `server/requirements.txt` (ADD)

```txt
# ... existing dependencies ...

# Semantic de-duplication
openai>=1.0.0           # OpenAI API for embeddings
numpy>=1.24.0           # Vector operations
pydantic[dotenv]>=2.0   # Config management
```

### Install

```bash
cd server
pip install -r requirements.txt
```

---

## ⚙️ Configuration

### Environment Variables

**File**: `server/.env.example` (ADD)

```bash
# ACE Server Configuration

# Semantic De-duplication
SEMANTIC_DEDUP_ENABLED=true
SEMANTIC_SIMILARITY_THRESHOLD=0.85
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_CACHE_ENABLED=true

# OpenAI API
OPENAI_API_KEY=sk-your-openai-api-key-here

# Existing settings...
```

### Production Configuration

```bash
# Create .env file
cp .env.example .env

# Edit with your API key
nano .env
```

---

## 🧪 Testing Strategy

### 1. Unit Tests

**File**: `server/tests/test_embedding_service.py` (NEW)

```python
import pytest
import numpy as np
from ace_server.services.embedding_service import EmbeddingService


@pytest.fixture
async def embedding_service():
    """Create embedding service for testing."""
    return EmbeddingService(
        api_key="test-key",
        cache_enabled=True
    )


@pytest.mark.asyncio
async def test_embedding_generation(embedding_service):
    """Test basic embedding generation."""
    text = "Use JWT tokens for authentication"
    embedding = await embedding_service.get_embedding(text)

    assert isinstance(embedding, np.ndarray)
    assert len(embedding) == 1536  # text-embedding-3-small dimension


@pytest.mark.asyncio
async def test_embedding_cache(embedding_service):
    """Test embedding caching."""
    text = "Use JWT tokens for authentication"

    # First call generates
    embedding1 = await embedding_service.get_embedding(text)

    # Second call uses cache
    embedding2 = await embedding_service.get_embedding(text)

    np.testing.assert_array_equal(embedding1, embedding2)

    stats = embedding_service.get_cache_stats()
    assert stats["cache_size"] == 1


@pytest.mark.asyncio
async def test_batch_embeddings(embedding_service):
    """Test batch embedding generation."""
    texts = [
        "Use JWT tokens for authentication",
        "Implement refresh token rotation",
        "Add rate limiting to API"
    ]

    embeddings = await embedding_service.get_embeddings_batch(texts)

    assert len(embeddings) == 3
    assert all(isinstance(e, np.ndarray) for e in embeddings)


def test_cosine_similarity(embedding_service):
    """Test cosine similarity calculation."""
    # Same vectors should have similarity of 1.0
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([1.0, 0.0, 0.0])

    similarity = embedding_service.cosine_similarity(vec1, vec2)
    assert similarity == 1.0

    # Orthogonal vectors should have similarity of 0.0
    vec3 = np.array([0.0, 1.0, 0.0])
    similarity = embedding_service.cosine_similarity(vec1, vec3)
    assert similarity == 0.0
```

**File**: `server/tests/test_curator_dedup.py` (NEW)

```python
import pytest
from ace_server.curator import Curator
from ace_server.services.embedding_service import EmbeddingService
from ace_server.types import PlaybookBullet, DeltaOperation, BulletSection


@pytest.fixture
async def curator():
    """Create curator with embedding service."""
    embedding_service = EmbeddingService(
        api_key="test-key",
        cache_enabled=True
    )

    return Curator(
        embedding_service=embedding_service,
        semantic_dedup_enabled=True,
        similarity_threshold=0.85
    )


@pytest.mark.asyncio
async def test_exact_duplicate_detection(curator):
    """Test exact duplicate detection."""
    playbook = {
        BulletSection.STRATEGIES: [
            PlaybookBullet(
                id="bullet-1",
                section=BulletSection.STRATEGIES,
                content="Use JWT tokens for authentication",
                helpful=5,
                harmful=0,
                confidence=1.0,
                observations=5,
                evidence=[],
                created_at="2025-01-01",
                last_used="2025-01-01"
            )
        ]
    }

    # Try to add exact duplicate
    is_dup = await curator._is_semantic_duplicate(
        "Use JWT tokens for authentication",
        BulletSection.STRATEGIES,
        playbook
    )

    assert is_dup is True


@pytest.mark.asyncio
async def test_semantic_duplicate_detection(curator):
    """Test semantic duplicate detection."""
    playbook = {
        BulletSection.STRATEGIES: [
            PlaybookBullet(
                id="bullet-1",
                section=BulletSection.STRATEGIES,
                content="Use JWT tokens for authentication",
                helpful=5,
                harmful=0,
                confidence=1.0,
                observations=5,
                evidence=[],
                created_at="2025-01-01",
                last_used="2025-01-01"
            )
        ]
    }

    # Try to add semantic duplicate (different wording)
    is_dup = await curator._is_semantic_duplicate(
        "Implement JSON Web Tokens for user auth",
        BulletSection.STRATEGIES,
        playbook
    )

    # Should be caught as duplicate (similarity > 0.85)
    assert is_dup is True


@pytest.mark.asyncio
async def test_non_duplicate_detection(curator):
    """Test that different content is not marked as duplicate."""
    playbook = {
        BulletSection.STRATEGIES: [
            PlaybookBullet(
                id="bullet-1",
                section=BulletSection.STRATEGIES,
                content="Use JWT tokens for authentication",
                helpful=5,
                harmful=0,
                confidence=1.0,
                observations=5,
                evidence=[],
                created_at="2025-01-01",
                last_used="2025-01-01"
            )
        ]
    }

    # Different content
    is_dup = await curator._is_semantic_duplicate(
        "Add rate limiting to prevent abuse",
        BulletSection.STRATEGIES,
        playbook
    )

    assert is_dup is False
```

### 2. Integration Tests

**File**: `server/tests/integration/test_full_cycle.py` (NEW)

```python
import pytest
from ace_server.main import app
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_semantic_dedup_in_learning_cycle():
    """Test full learning cycle with semantic de-duplication."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Submit learning with JWT pattern
        response1 = await client.post("/api/learn", json={
            "task": "Implement authentication",
            "trajectory": [
                {"step": "Research", "action": "Researched JWT"},
                {"step": "Implementation", "action": "Added JWT auth"}
            ],
            "success": True,
            "output": "Use JWT tokens for authentication"
        })

        assert response1.status_code == 200

        # Retrieve playbook, should have 1 bullet
        response2 = await client.get("/api/playbook")
        playbook1 = response2.json()

        strategies = playbook1["strategies_and_hard_rules"]
        assert len(strategies) == 1

        # Submit learning with semantic duplicate (different wording)
        response3 = await client.post("/api/learn", json={
            "task": "Add auth to API",
            "trajectory": [
                {"step": "Implementation", "action": "Implemented JSON Web Tokens"}
            ],
            "success": True,
            "output": "Implement JSON Web Tokens for user authentication"
        })

        assert response3.status_code == 200

        # Retrieve playbook again, should still have 1 bullet (duplicate caught)
        response4 = await client.get("/api/playbook")
        playbook2 = response4.json()

        strategies = playbook2["strategies_and_hard_rules"]
        assert len(strategies) == 1  # Duplicate was not added
```

### 3. Performance Tests

**File**: `server/tests/performance/test_embedding_performance.py` (NEW)

```python
import pytest
import time
from ace_server.services.embedding_service import EmbeddingService


@pytest.mark.asyncio
async def test_embedding_cache_performance():
    """Test that caching provides significant speedup."""
    service = EmbeddingService(api_key="test-key", cache_enabled=True)

    text = "Use JWT tokens for authentication"

    # First call (uncached)
    start = time.time()
    await service.get_embedding(text)
    uncached_time = time.time() - start

    # Second call (cached)
    start = time.time()
    await service.get_embedding(text)
    cached_time = time.time() - start

    # Cached should be at least 10x faster
    assert cached_time < uncached_time / 10

    print(f"Uncached: {uncached_time:.3f}s, Cached: {cached_time:.6f}s")
```

---

## 🚀 Deployment

### 1. Development Environment

```bash
# Navigate to server
cd server/

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add OPENAI_API_KEY

# Run tests
pytest tests/ -v

# Start server
uvicorn ace_server.main:app --reload
```

### 2. Production Deployment

```bash
# Update dependencies
pip install -r requirements.txt

# Set environment variables
export SEMANTIC_DEDUP_ENABLED=true
export SEMANTIC_SIMILARITY_THRESHOLD=0.85
export EMBEDDING_MODEL=text-embedding-3-small
export OPENAI_API_KEY=sk-your-production-key

# Run with production settings
uvicorn ace_server.main:app --host 0.0.0.0 --port 9000 --workers 4
```

### 3. Docker Deployment

**File**: `server/Dockerfile` (MODIFY)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Environment variables (override at runtime)
ENV SEMANTIC_DEDUP_ENABLED=true
ENV SEMANTIC_SIMILARITY_THRESHOLD=0.85
ENV EMBEDDING_MODEL=text-embedding-3-small

# Run server
CMD ["uvicorn", "ace_server.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

**File**: `server/docker-compose.yml` (MODIFY)

```yaml
version: '3.8'

services:
  ace-server:
    build: .
    ports:
      - "9000:9000"
    environment:
      - SEMANTIC_DEDUP_ENABLED=true
      - SEMANTIC_SIMILARITY_THRESHOLD=0.85
      - EMBEDDING_MODEL=text-embedding-3-small
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    env_file:
      - .env
```

---

## 💰 Cost Analysis

### Embedding API Costs

**Model**: text-embedding-3-small
**Price**: $0.00002 per 1K tokens

**Example calculations**:

```
Average bullet: 50 tokens
Cost per bullet: $0.000001 (one millionth of a dollar)

10 bullets: $0.00001
100 bullets: $0.0001
1,000 bullets: $0.001
10,000 bullets: $0.01
```

### With Caching

**First computation**: $0.000001 per bullet
**Subsequent comparisons**: $0 (uses cache)

**Example scenario**:
- Add 100 new bullets over time
- Each compared against 500 existing bullets
- **Total cost**: 100 new × $0.000001 = **$0.0001** (ten cents per million bullets!)
- Existing bullets use cache: $0

### Monthly Cost Estimate

**Active development** (500 bullets/month):
- New bullets: 500 × $0.000001 = **$0.0005/month**
- Comparisons: cached, $0

**Heavy usage** (5,000 bullets/month):
- New bullets: 5,000 × $0.000001 = **$0.005/month** (half a cent!)

**Result**: Cost is negligible, ~$0.01/month even with heavy usage.

---

## 📊 Monitoring

### Metrics to Track

```python
# Add to server/metrics.py
from prometheus_client import Counter, Histogram

# Semantic dedup metrics
semantic_dedup_checks = Counter(
    'semantic_dedup_checks_total',
    'Total semantic duplicate checks performed'
)

semantic_duplicates_found = Counter(
    'semantic_duplicates_found_total',
    'Total semantic duplicates detected'
)

embedding_generation_time = Histogram(
    'embedding_generation_seconds',
    'Time to generate embeddings'
)

embedding_cache_hits = Counter(
    'embedding_cache_hits_total',
    'Total embedding cache hits'
)

embedding_cache_misses = Counter(
    'embedding_cache_misses_total',
    'Total embedding cache misses'
)
```

### Dashboard

Monitor in production:
- Duplicate detection rate
- Embedding cache hit rate
- API cost tracking
- Performance metrics

---

## 🔄 Migration Path

### Phase 1: Deploy with Feature Flag (Week 1)

```bash
# Deploy with feature disabled
SEMANTIC_DEDUP_ENABLED=false

# Verify server health
curl http://localhost:9000/health
```

### Phase 2: Enable for Testing (Week 2)

```bash
# Enable for internal testing
SEMANTIC_DEDUP_ENABLED=true
SEMANTIC_SIMILARITY_THRESHOLD=0.85
```

Test with real workloads, monitor:
- Duplicate detection accuracy
- Performance impact
- Cost

### Phase 3: Production Rollout (Week 3)

```bash
# Full production deployment
SEMANTIC_DEDUP_ENABLED=true
SEMANTIC_SIMILARITY_THRESHOLD=0.85
```

Monitor for 1 week, adjust threshold if needed.

### Rollback Plan

If issues arise:

```bash
# Instant rollback
SEMANTIC_DEDUP_ENABLED=false

# Or adjust threshold
SEMANTIC_SIMILARITY_THRESHOLD=0.95  # More strict
```

---

## 🎯 Success Criteria

### Functional
- ✅ Semantic duplicates detected with 85% threshold
- ✅ Exact duplicates still caught (fallback works)
- ✅ No false negatives (distinct bullets not marked as duplicate)
- ✅ Acceptable false positives (<5% of comparisons)

### Performance
- ✅ Embedding generation <500ms (with caching)
- ✅ Cache hit rate >90% after warmup
- ✅ No noticeable latency impact on learning cycle

### Cost
- ✅ Monthly cost <$1 for typical usage
- ✅ Cost scales linearly with new bullets
- ✅ Cache reduces cost to near-zero

### Quality
- ✅ Playbook size reduced by 15-30% (fewer duplicates)
- ✅ No degradation in pattern quality
- ✅ User satisfaction maintained

---

## 📚 References

- **Architecture**: [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Enhancement Roadmap**: [ENHANCEMENT_ROADMAP.md](./ENHANCEMENT_ROADMAP.md)
- **OpenAI Embeddings**: https://platform.openai.com/docs/guides/embeddings
- **Cosine Similarity**: https://en.wikipedia.org/wiki/Cosine_similarity

---

## ✅ Implementation Checklist

### Server-Side
- [ ] Create `embedding_service.py` with OpenAI integration
- [ ] Update `curator.py` with semantic dedup logic
- [ ] Add configuration in `config.py`
- [ ] Wire up in `main.py`
- [ ] Add dependencies to `requirements.txt`
- [ ] Create `.env.example` with new settings

### Testing
- [ ] Unit tests for embedding service
- [ ] Unit tests for curator dedup logic
- [ ] Integration tests for full cycle
- [ ] Performance tests for caching
- [ ] Manual testing with real workloads

### Documentation
- [ ] Update server README with new features
- [ ] Document configuration options
- [ ] Add troubleshooting guide
- [ ] Update deployment docs

### Deployment
- [ ] Deploy to dev environment (feature flag OFF)
- [ ] Enable feature flag for testing
- [ ] Monitor metrics for 1 week
- [ ] Roll out to production
- [ ] Update MCP client docs (no code changes needed)

---

**Estimated Timeline**: 3-4 days
**Effort**: Medium (infrastructure exists, mainly server-side)
**Risk**: Low (feature flag, fallback to exact match)
**Impact**: High (prevents playbook bloat, reaches 98% compliance)
