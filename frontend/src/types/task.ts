export type TaskStatus = "PENDING" | "PROCESSING" | "SUCCESS" | "FAILURE" | "REVOKED";

export type TaskStatusResponse = {
  task_id: string;
  status: TaskStatus | string;
  progress: number;
  message?: string | null;
  result_url?: string | null;
  warnings: string[];
};

export type UploadTaskResponse = TaskStatusResponse;

