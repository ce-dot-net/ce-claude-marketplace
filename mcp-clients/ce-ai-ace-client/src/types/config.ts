/**
 * ACE Configuration
 */

export interface ACEConfig {
  // Server connection (for remote storage)
  serverUrl: string;
  apiToken: string;
  projectId: string;

  // Curation thresholds (from ACE paper)
  similarityThreshold: number;  // Default: 0.85
  confidenceThreshold: number;  // Default: 0.30
}

export function getConfig(): ACEConfig {
  return {
    serverUrl: process.env.ACE_SERVER_URL || 'http://localhost:9000',
    apiToken: process.env.ACE_API_TOKEN || '',
    projectId: process.env.ACE_PROJECT_ID || '',
    similarityThreshold: parseFloat(process.env.ACE_SIMILARITY_THRESHOLD || '0.85'),
    confidenceThreshold: parseFloat(process.env.ACE_CONFIDENCE_THRESHOLD || '0.30')
  };
}
