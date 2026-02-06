import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  root: "src",

  server: {
    // чтобы можно было открыть dev-сервер не только с localhost
    host: true,
    port: 5173,
    strictPort: true,

    // разрешаем доступ по вашему домену (иначе будет "Blocked request. This host is not allowed.")
    allowedHosts: [
      "scen4ri0.info",
      "www.scen4ri0.info",
      "localhost",
      "127.0.0.1",
    ],
  },

  // если используешь `vite preview --host`, лучше сразу разрешить те же хосты и там
  preview: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: [
      "scen4ri0.info",
      "www.scen4ri0.info",
      "localhost",
      "127.0.0.1",
    ],
  },

  build: {
    rollupOptions: {
      input: {
        home: resolve(__dirname, "src/index.html"),
        quiz1: resolve(__dirname, "src/quiz1.html"),
        quiz2: resolve(__dirname, "src/quiz2.html"),
        quiz3: resolve(__dirname, "src/quiz3.html"),
        quiz4: resolve(__dirname, "src/quiz4.html"),
        leaderboard: resolve(__dirname, "src/leaderboard.html"),
      },
    },
  },
});
