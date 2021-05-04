import { DefaultLayout, AuthLayout } from "@/components/layouts";

export const publicRoute = [
  {
    path: "*",
    component: () =>
      import(/* webpackChunkName: "errors-404" */ "@/views/error/NotFound.vue")
  },
  {
    path: "/login",
    component: AuthLayout,
    meta: { title: "Login", icon: "view_compact", group: "auth" },
    children: [
      {
        path: "/login",
        name: "Login",
        component: () =>
          import(/* webpackChunkName: "auth-login" */ "@/auth/Login.vue")
      }
    ]
  },
  {
    path: "/register",
    component: AuthLayout,
    meta: { title: "Register", icon: "view_compact", group: "auth" },
    children: [
      {
        path: "/register",
        name: "Register",
        component: () =>
          import(/* webpackChunkName: "auth-register" */ "@/auth/Register.vue")
      }
    ]
  },
  {
    path: "/404",
    name: "404",
    meta: { title: "Not Found" },
    component: () =>
      import(/* webpackChunkName: "errors-404" */ "@/views/error/NotFound.vue")
  },
  {
    path: "/500",
    name: "500",
    meta: { title: "Server Error" },
    component: () =>
      import(/* webpackChunkName: "errors-500" */ "@/views/error/Error.vue")
  }
];

// NOTE: The order in which routes are added to the list matters when evaluated. For example, /jobs/report will take precendence over /jobs/:name.
export const protectedRoute = [
  {
    path: "/",
    component: DefaultLayout,
    meta: { title: "Dispatch", group: "jobs", icon: "" },
    redirect: "/gantt",
    children: [
      {
        path: "/403",
        name: "Forbidden",
        meta: { title: "Access Denied", hiddenInMenu: true },
        component: () =>
          import(/* webpackChunkName: "error-403" */ "@/views/error/Deny.vue")
      }
    ]
  },
  {
    path: "/jobs/status",
    meta: { title: "Status", icon: "", requiresAuth: true },
    component: () =>
      import(/* webpackChunkName: "jobs-status" */ "@/job/Status.vue")
  },

  {
    path: "/jobs/report",
    meta: { title: "Report", icon: "", requiresAuth: true },
    component: () =>
      import(/* webpackChunkName: "jobs-report" */ "@/job/ReportForm.vue")
  },
  {
    path: "/jobs/types",
    component: DefaultLayout,
    meta: {
      title: "Job Types",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true
    }
  },
  {
    path: "/gantt",
    component: DefaultLayout,
    meta: {
      title: "gantt",
      icon: "view_compact",
      group: "gantt",
      requiresAuth: true
    },
    children: [
      {
        path: "/gantt",
        name: "Gantt",
        component: () =>
          import(/* webpackChunkName: "job-dashboard" */ "@/gantt/Gantt.vue")
      }
    ]
  },
  {
    path: "/jobs",
    component: DefaultLayout,
    meta: {
      title: "Jobs",
      icon: "view_compact",
      group: "jobs",
      requiresAuth: true
    },
    children: [
      {
        path: "/jobs",
        name: "JobTable",
        component: () =>
          import(/* webpackChunkName: "job-table" */ "@/job/Table.vue")
      }
    ]
  },
  {
    path: "/services",
    component: DefaultLayout,
    meta: {
      title: "Services",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true
    },
    children: [
      {
        path: "/services",
        name: "ServiceTable",
        component: () =>
          import(/* webpackChunkName: "service-table" */ "@/service/Table.vue")
      }
    ]
  },
  {
    path: "/service_plugin",
    component: DefaultLayout,
    meta: {
      title: "Service Plugins",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true
    },
    children: [
      {
        path: "/service_plugin",
        name: "ServicePluginTable",
        component: () =>
          import(
            /* webpackChunkName: "service-table" */ "@/service_plugin/Table.vue"
          )
      }
    ]
  },
  {
    path: "/workers",
    component: DefaultLayout,
    meta: {
      title: "Workers",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true
    },
    children: [
      {
        path: "/workers",
        name: "WorkerTable",
        component: () =>
          import(/* webpackChunkName: "worker-table" */ "@/worker/Table.vue")
      }
    ]
  },
  {
    path: "/teams",
    component: DefaultLayout,
    meta: {
      title: "Teams",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true
    },
    children: [
      {
        path: "/teams",
        name: "TeamTable",
        component: () =>
          import(/* webpackChunkName: "team-table" */ "@/team/Table.vue")
      }
    ]
  },
  {
    path: "/tags",
    component: DefaultLayout,
    meta: {
      title: "Tags",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true
    },
    children: [
      {
        path: "/tags",
        name: "TagTable",
        component: () =>
          import(/* webpackChunkName: "tag-table" */ "@/tag/Table.vue")
      }
    ]
  },
  {
    path: "/search",
    component: DefaultLayout,
    meta: {
      title: "Search",
      icon: "view_compact",
      group: "search",
      requiresAuth: true
    },
    children: [
      {
        path: "/search",
        name: "ResultList",
        component: () =>
          import(
            /* webpackChunkName: "search-result-list" */ "@/search/ResultList.vue"
          )
      }
    ]
  },
  {
    path: "/plugins",
    component: DefaultLayout,
    meta: {
      title: "Plugins",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true
    },
    children: [
      {
        path: "/plugins",
        name: "PluginTable",
        component: () =>
          import(/* webpackChunkName: "routing-table" */ "@/plugin/Table.vue")
      }
    ]
  },
  {
    path: "/locations",
    component: DefaultLayout,
    meta: {
      title: "Locations",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true
    },
    children: [
      {
        path: "/locations",
        name: "LocationTable",
        component: () =>
          import(/* webpackChunkName: "routing-table" */ "@/location/Table.vue")
      }
    ]
  },
  {
    path: "/users",
    component: DefaultLayout,
    meta: {
      title: "Users",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true
    },
    children: [
      {
        path: "/users",
        name: "UserTable",
        component: () =>
          import(/* webpackChunkName: "routing-table" */ "@/auth/Table.vue")
      }
    ]
  }
];
