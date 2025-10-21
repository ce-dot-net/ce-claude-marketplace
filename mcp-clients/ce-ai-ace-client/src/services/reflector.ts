/**
 * Reflector Service - Analyzes execution outcomes and generates delta operations
 *
 * This is the CORE innovation of ACE - learning from execution feedback
 * Paper Section 3: "The Reflector critiques traces to extract lessons"
 */

import { ExecutionTrace, Reflection, PlaybookBullet } from '../types/pattern.js';

export class ReflectorService {
  /**
   * Analyze execution outcome and generate delta operations
   *
   * Takes an execution trace and identifies:
   * 1. Which playbook bullets were helpful
   * 2. Which playbook bullets were harmful
   * 3. New insights to add to playbook
   * 4. Bullets to update or delete
   */
  async analyzeExecution(
    trace: ExecutionTrace,
    playbook: PlaybookBullet[],
    requestSampling: (messages: any[]) => Promise<any>
  ): Promise<Reflection> {
    const prompt = this.buildReflectionPrompt(trace, playbook);

    try {
      const response = await requestSampling([{
        role: 'user',
        content: prompt
      }]);

      const text = response.content[0].text;
      const jsonMatch = text.match(/\{[\s\S]*\}/);

      if (!jsonMatch) {
        throw new Error('Failed to parse reflection from LLM');
      }

      return JSON.parse(jsonMatch[0]) as Reflection;
    } catch (error) {
      console.error('Error in reflection:', error);
      throw error;
    }
  }

  /**
   * Iterative refinement of reflection (multi-pass)
   * Paper: "optionally refining them across multiple iterations"
   */
  async refineReflection(
    initialReflection: Reflection,
    trace: ExecutionTrace,
    requestSampling: (messages: any[]) => Promise<any>,
    iterations: number = 2
  ): Promise<Reflection> {
    let refined = initialReflection;

    for (let i = 0; i < iterations; i++) {
      const prompt = `You are refining a reflection from the ACE (Agentic Context Engineering) system.

Review and improve this reflection:

${JSON.stringify(refined, null, 2)}

Original execution trace:
${JSON.stringify(trace, null, 2)}

Your task:
1. Make delta operations more specific and actionable
2. Verify confidence scores are accurate
3. Merge similar operations if redundant
4. Remove vague or duplicate insights
5. Ensure evidence is concrete

Return improved JSON with same structure:
{
  "operations": [
    {
      "type": "ADD" | "UPDATE" | "DELETE",
      "section": "strategies_and_hard_rules" | "useful_code_snippets" | "troubleshooting_and_pitfalls" | "apis_to_use",
      "content": "...",
      "bullet_id": "ctx-xxxxx",
      "helpful_delta": 0 | 1,
      "harmful_delta": 0 | 1,
      "confidence": 0.0-1.0,
      "evidence": ["..."],
      "reason": "..."
    }
  ],
  "summary": "..."
}`;

      try {
        const response = await requestSampling([{
          role: 'user',
          content: prompt
        }]);

        const text = response.content[0].text;
        const jsonMatch = text.match(/\{[\s\S]*\}/);

        if (jsonMatch) {
          refined = JSON.parse(jsonMatch[0]);
        }
      } catch (error) {
        console.error(`Refinement iteration ${i + 1} failed:`, error);
        // Continue with current refinement
      }
    }

    return refined;
  }

  /**
   * Build reflection prompt for LLM
   */
  private buildReflectionPrompt(
    trace: ExecutionTrace,
    playbook: PlaybookBullet[]
  ): string {
    const bulletsUsed = trace.playbook_used
      .map(id => {
        const bullet = playbook.find(b => b.id === id);
        if (!bullet) return null;
        return {
          id,
          section: bullet.section,
          content: bullet.content,
          helpful: bullet.helpful,
          harmful: bullet.harmful
        };
      })
      .filter(b => b !== null);

    return `You are the Reflector agent in the ACE (Agentic Context Engineering) system.

Analyze this execution trace and identify lessons learned:

**Task**: ${trace.task}

**Execution Trajectory**:
${JSON.stringify(trace.trajectory, null, 2)}

**Result**:
- Success: ${trace.result.success}
- Output: ${trace.result.output}
- Error: ${trace.result.error || 'None'}

**Playbook Bullets Used During Execution**:
${bulletsUsed.length > 0
  ? bulletsUsed.map(b => `[${b!.id}] (${b!.section}) helpful=${b!.helpful} harmful=${b!.harmful}\n${b!.content}`).join('\n\n')
  : 'No bullets were consulted'}

Your task:
1. **Identify helpful bullets**: Which bullets led to success? Mark them with helpful_delta=1
2. **Identify harmful bullets**: Which bullets caused errors or mislead? Mark them with harmful_delta=1
3. **Extract new insights**: What NEW knowledge should be added to the playbook?
   - Strategies/rules that emerged
   - Code snippets that worked
   - Pitfalls discovered
   - API patterns validated
4. **Generate delta operations**: ADD/UPDATE/DELETE operations to improve playbook

For UPDATE operations:
- helpful_delta=1 if the bullet helped achieve success
- harmful_delta=1 if the bullet caused or contributed to errors
- helpful_delta=0 and harmful_delta=0 if uncertain

For ADD operations:
- Choose the right section (strategies_and_hard_rules, useful_code_snippets, troubleshooting_and_pitfalls, apis_to_use)
- Set confidence based on how certain you are (0.0-1.0)
- Provide concrete evidence (error messages, line numbers, test results)

For DELETE operations:
- Only suggest if bullet is consistently harmful or completely wrong

Return ONLY JSON with no additional text:
{
  "operations": [
    {
      "type": "ADD",
      "section": "strategies_and_hard_rules",
      "content": "Always check if JWT library is installed before importing",
      "confidence": 0.9,
      "evidence": ["ImportError: No module named 'jwt' in line 5"],
      "reason": "Task failed due to missing dependency"
    },
    {
      "type": "UPDATE",
      "bullet_id": "ctx-12345",
      "helpful_delta": 0,
      "harmful_delta": 1,
      "reason": "Bullet suggested using jwt without checking installation"
    }
  ],
  "summary": "Task failed due to missing jwt dependency. Added strategy to check library installation. Marked misleading bullet as harmful."
}`;
  }
}
