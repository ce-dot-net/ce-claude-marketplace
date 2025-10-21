/**
 * ACE Configuration
 */

import { loadConfig } from '../services/config-loader.js';

export interface ACEConfig {
  // Server connection (for remote storage)
  serverUrl: string;
  apiToken: string;
  projectId: string;

  // Curation thresholds
  similarityThreshold: number;  // Default: 0.85
  confidenceThreshold: number;  // Default: 0.30
}

export function getConfig(): ACEConfig {
  // Load config from files and environment variables
  const fileConfig = loadConfig();

  return {
    serverUrl: fileConfig.serverUrl,
    apiToken: fileConfig.apiToken,
    projectId: fileConfig.projectId,
    similarityThreshold: parseFloat(process.env.ACE_SIMILARITY_THRESHOLD || '0.85'),
    confidenceThreshold: parseFloat(process.env.ACE_CONFIDENCE_THRESHOLD || '0.30')
  };
}
