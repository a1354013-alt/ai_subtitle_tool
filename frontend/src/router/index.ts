import { createRouter, createWebHistory } from "vue-router";

const HomePage = () => import("@/pages/HomePage.vue");
const TaskStatusPage = () => import("@/pages/TaskStatusPage.vue");
const SubtitlePage = () => import("@/pages/SubtitlePage.vue");
const DownloadPage = () => import("@/pages/DownloadPage.vue");

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomePage },
    { path: "/task/:taskId", name: "task", component: TaskStatusPage, props: true },
    { path: "/task/:taskId/subtitles", name: "subtitles", component: SubtitlePage, props: true },
    { path: "/task/:taskId/downloads", name: "downloads", component: DownloadPage, props: true },
  ],
});

export default router;

