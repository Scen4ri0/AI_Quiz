import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  root: "src",
  server: { port: 5173 },
  build: {
    rollupOptions: {
      input: {
        home: resolve(__dirname, "src/index.html"),
        quiz1: resolve(__dirname, "src/quiz1.html"),
        quiz2: resolve(__dirname, "src/quiz2.html"),
        leaderboard: resolve(__dirname, "src/leaderboard.html"),
      }
    }
  }
});
