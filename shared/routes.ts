import { z } from "zod";
import { insertScriptSchema, insertLessonSchema, scripts, lessons } from "./schema";

export const errorSchemas = {
  validation: z.object({
    message: z.string(),
    field: z.string().optional(),
  }),
  notFound: z.object({
    message: z.string(),
  }),
  internal: z.object({
    message: z.string(),
  }),
};

export const api = {
  scripts: {
    list: {
      method: "GET" as const,
      path: "/api/scripts",
      responses: {
        200: z.array(z.custom<typeof scripts.$inferSelect>()),
      },
    },
    create: {
      method: "POST" as const,
      path: "/api/scripts",
      input: insertScriptSchema,
      responses: {
        201: z.custom<typeof scripts.$inferSelect>(),
        400: errorSchemas.validation,
      },
    },
    get: {
      method: "GET" as const,
      path: "/api/scripts/:id",
      responses: {
        200: z.custom<typeof scripts.$inferSelect>(),
        404: errorSchemas.notFound,
      },
    },
  },
  lessons: {
    list: {
      method: "GET" as const,
      path: "/api/lessons",
      responses: {
        200: z.array(z.custom<typeof lessons.$inferSelect>()),
      },
    },
    get: {
      method: "GET" as const,
      path: "/api/lessons/:id",
      responses: {
        200: z.custom<typeof lessons.$inferSelect>(),
        404: errorSchemas.notFound,
      },
    },
  },
  execute: {
    method: "POST" as const,
    path: "/api/execute",
    input: z.object({ code: z.string() }),
    responses: {
      200: z.object({ output: z.string(), error: z.string().optional() }),
      400: errorSchemas.validation,
    },
  },
};

export function buildUrl(path: string, params?: Record<string, string | number>): string {
  let url = path;
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (url.includes(`:${key}`)) {
        url = url.replace(`:${key}`, String(value));
      }
    });
  }
  return url;
}
