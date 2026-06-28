import { createRouter, createWebHistory } from "vue-router";
import AgentView from "../views/AgentView.vue";
import DashboardView from "../views/DashboardView.vue";
import DevicesView from "../views/DevicesView.vue";
import RagView from "../views/RagView.vue";
import SettingsView from "../views/SettingsView.vue";
import VisionView from "../views/VisionView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/dashboard" },
    { path: "/dashboard", name: "dashboard", component: DashboardView },
    { path: "/vision", name: "vision", component: VisionView },
    { path: "/rag", name: "rag", component: RagView },
    { path: "/agent", name: "agent", component: AgentView },
    { path: "/devices", name: "devices", component: DevicesView },
    { path: "/settings", name: "settings", component: SettingsView }
  ]
});

export default router;
