import Vue from 'vue';
import VueRouter from 'vue-router';
import Play from '@/components/pages/Play.vue';
import Host from '@/components/pages/Host.vue';
import Home from '@/components/pages/Home.vue';
import SessionList from '@/components/pages/SessionList.vue';
import QuizList from '@/components/pages/QuizList.vue';

Vue.use(VueRouter);

const routes = [
  // Home
  {
    path: '/',
    component: Home,
    meta: {
      title: 'Fobbage',
    },
    children: [
      // Play
      {
        path: '/play',
        component: SessionList,
        children: [
          {
            path: '/:id(\\d+)?',
            component: Play,
            props: (route) => ({ id: Number(route.params.id) }),
          },
        ],
      },
      // Host
      {
        path: '/host',
        component: QuizList,
        children: [
          {
            path: '/:id(\\d+)?',
            component: Host,
            props: (route) => ({ id: Number(route.params.id) }),
          },
        ],
      },
    ],
  },
  // login  pages
  {
    path: '/login',
    name: 'login',
    component: () => import(/* webpackChunkName: "login" */ '@/components/pages/Login.vue'),
    meta: {
      title: 'Fobbage - Login',
    },
  },
  // login  pages
  {
    path: '/logout',
    name: 'logout',
    component: () => import(/* webpackChunkName: "login" */ '@/components/pages/Logout.vue'),
    meta: {
      title: 'Fobbage - Logout',
    },
  },
  // register  pages
  {
    path: '/register',
    name: 'register',
    component: () => import(/* webpackChunkName: "login" */ '@/components/pages/Register.vue'),
    meta: {
      title: 'Fobbage - Register',
    },
  },
];

const router = new VueRouter({
  mode: 'history',
  base: process.env.BASE_URL,
  routes,
});

const isAuthenticated = () => localStorage.getItem('accessToken');

router.beforeEach(async (to, from, next) => {
  if (to.matched.some((route) => route.meta.requiresAuth)) {
    // Route is protected
    if (!isAuthenticated()) {
      // Not authenticated. Go to login page.
      if (from.path !== 'login') {
        next({
          name: 'login',
          params: { nextUrl: to.fullPath },
        });
      }
    } else {
      // Authenticated, go ahead with the navigation.
      next();
    }
  } else {
    // Route is not protected
    next();
  }
});

export default router;
