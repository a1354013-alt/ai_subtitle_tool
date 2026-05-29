export type APIError = {
  message: string;
  status?: number;
  detail?: unknown;
  error_code?: string;
  suggestion?: string;
};

export type ErrorResponse = {
  success: false;
  error_code: string;
  message: string;
  suggestion: string;
};

