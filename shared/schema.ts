import { pgTable, text, serial, timestamp, boolean } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const scripts = pgTable("scripts", {
  id: serial("id").primaryKey(),
  title: text("title").notNull().default("Untitled Script"),
  content: text("content").notNull(),
  output: text("output"),
  createdAt: timestamp("created_at").defaultNow(),
});

export const lessons = pgTable("lessons", {
  id: serial("id").primaryKey(),
  title: text("title").notNull(),
  description: text("description").notNull(),
  content: text("content").notNull(), // Markdown content
  exampleCode: text("example_code").notNull(),
  difficulty: text("difficulty").notNull().default("beginner"),
  order: serial("order").notNull(),
});

export const insertScriptSchema = createInsertSchema(scripts).omit({ id: true, createdAt: true });
export const insertLessonSchema = createInsertSchema(lessons).omit({ id: true });

export type Script = typeof scripts.$inferSelect;
export type InsertScript = z.infer<typeof insertScriptSchema>;
export type Lesson = typeof lessons.$inferSelect;
export type InsertLesson = z.infer<typeof insertLessonSchema>;

export type ExecuteRequest = {
  code: string;
};

export type ExecuteResponse = {
  output: string;
  error?: string;
};
