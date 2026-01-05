import type { Express } from "express";
import type { Server } from "http";
import { storage } from "./storage";
import { api } from "@shared/routes";
import { z } from "zod";
import { exec } from "child_process";
import fs from "fs";
import path from "path";
import os from "os";

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  
  // Scripts
  app.get(api.scripts.list.path, async (req, res) => {
    const scripts = await storage.getScripts();
    res.json(scripts);
  });

  app.get(api.scripts.get.path, async (req, res) => {
    const script = await storage.getScript(Number(req.params.id));
    if (!script) return res.status(404).json({ message: "Script not found" });
    res.json(script);
  });

  app.post(api.scripts.create.path, async (req, res) => {
    try {
      const input = api.scripts.create.input.parse(req.body);
      const script = await storage.createScript(input);
      res.status(201).json(script);
    } catch (err) {
      if (err instanceof z.ZodError) {
        return res.status(400).json({
          message: err.errors[0].message,
          field: err.errors[0].path.join('.'),
        });
      }
      throw err;
    }
  });

  // Lessons
  app.get(api.lessons.list.path, async (req, res) => {
    const lessons = await storage.getLessons();
    res.json(lessons);
  });

  app.get(api.lessons.get.path, async (req, res) => {
    const lesson = await storage.getLesson(Number(req.params.id));
    if (!lesson) return res.status(404).json({ message: "Lesson not found" });
    res.json(lesson);
  });

  // Execute
  app.post(api.execute.path, async (req, res) => {
    try {
      const { code } = req.body;
      if (!code) return res.status(400).json({ message: "Code is required" });

      // Create a temporary file
      const tmpDir = os.tmpdir();
      const fileName = `script_${Date.now()}.py`;
      const filePath = path.join(tmpDir, fileName);

      fs.writeFileSync(filePath, code);

      // Execute python script with timeout
      exec(`python3 ${filePath}`, { timeout: 5000 }, (error, stdout, stderr) => {
        // Cleanup temp file
        fs.unlink(filePath, () => {});

        if (error) {
          // If executed but failed (non-zero exit), stderr usually has the info
          // If timeout or other error, error.message has it
          const output = stderr || error.message;
          return res.json({ output, error: "Execution failed" });
        }
        
        res.json({ output: stdout || stderr });
      });

    } catch (err) {
      res.status(500).json({ message: "Internal server error" });
    }
  });

  await seedDatabase();

  return httpServer;
}

async function seedDatabase() {
  const existingLessons = await storage.getLessons();
  if (existingLessons.length === 0) {
    await storage.createLesson({
      title: "1. Hello, World!",
      description: "Learn how to print text to the console.",
      content: "# Hello, World!\n\nThe `print()` function is used to output text.\n\n```python\nprint('Hello, World!')\n```",
      exampleCode: "print('Hello, Replit!')",
      difficulty: "beginner",
      order: 1
    });
    
    await storage.createLesson({
      title: "2. Variables",
      description: "Storing data in variables.",
      content: "# Variables\n\nVariables are containers for storing data values.\n\n```python\nx = 5\ny = 'John'\nprint(x)\nprint(y)\n```",
      exampleCode: "name = 'Pythonista'\nprint(f'Hello, {name}!')",
      difficulty: "beginner",
      order: 2
    });

    await storage.createLesson({
      title: "3. Loops",
      description: "Repeating code with loops.",
      content: "# Loops\n\nA for loop is used for iterating over a sequence.\n\n```python\nfruits = ['apple', 'banana', 'cherry']\nfor x in fruits:\n  print(x)\n```",
      exampleCode: "for i in range(5):\n    print(f'Number: {i}')",
      difficulty: "beginner",
      order: 3
    });
  }
}
