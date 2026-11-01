import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('../views/Home.vue'), meta: { title: '工作台' } },
  { path: '/reports', component: () => import('../views/Reports.vue'), meta: { title: '研究报告' } },
  {
    path: '/reports/:taskId',
    component: () => import('../views/ReportDetail.vue'),
    meta: { title: '研究报告详情' },
  },
  { path: '/history', component: () => import('../views/History.vue'), meta: { title: '历史任务' } },
  { path: '/paper', component: () => import('../views/Paper.vue'), meta: { title: '模拟交易' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · FinAgent Lab` : 'FinAgent Lab'
})

export default router
