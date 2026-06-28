import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

const defaultTargets = {
  rag: "http://127.0.0.1:8095",
  agent: "http://127.0.0.1:8096",
  voice: "http://127.0.0.1:8093",
  edge: "http://127.0.0.1:8092",
  sensor: "http://127.0.0.1:8091",
  stream: "http://127.0.0.1:8081",
  backend: "http://127.0.0.1:18080"
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = {
    rag: env.VITE_RAG_TARGET || defaultTargets.rag,
    agent: env.VITE_AGENT_TARGET || defaultTargets.agent,
    voice: env.VITE_VOICE_TARGET || defaultTargets.voice,
    edge: env.VITE_EDGE_TARGET || defaultTargets.edge,
    sensor: env.VITE_SENSOR_TARGET || defaultTargets.sensor,
    stream: env.VITE_STREAM_TARGET || defaultTargets.stream,
    backend: env.VITE_BACKEND_TARGET || defaultTargets.backend
  };

  return {
    plugins: [vue()],
    server: {
      proxy: {
        "/api/rag": {
          target: target.rag,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/rag/, "")
        },
        "/api/agent": {
          target: target.agent,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/agent/, "")
        },
        "/api/voice": {
          target: target.voice,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/voice/, "")
        },
        "/api/edge": {
          target: target.edge,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/edge/, "")
        },
        "/api/sensor": {
          target: target.sensor,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/sensor/, "")
        },
        "/api/backend": {
          target: target.backend,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/backend/, "")
        },
        "/stream/mjpeg": {
          target: target.stream,
          changeOrigin: true,
          rewrite: () => "/stream"
        },
        "/stream/snapshot": {
          target: target.stream,
          changeOrigin: true,
          rewrite: () => "/snapshot"
        }
      }
    }
  };
});
