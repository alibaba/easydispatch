import { DefaultLayout, AuthLayout } from "@/components/layouts";

export const publicRoute = [
  {
    path: "*",
    component: () =>
      import(/* webpackChunkName: "errors-404" */ "@/views/error/NotFound.vue"),
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
          import(/* webpackChunkName: "auth-login" */ "@/auth/Login.vue"),
      },
    ],
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
          import(/* webpackChunkName: "auth-register" */ "@/auth/Register.vue"),
      },
    ],
  }, 
  {
    path: "/404",
    name: "404",
    meta: { title: "Not Found" },
    component: () =>
      import(/* webpackChunkName: "errors-404" */ "@/views/error/NotFound.vue"),
  },
  {
    path: "/500",
    name: "500",
    meta: { title: "Server Error" },
    component: () =>
      import(/* webpackChunkName: "errors-500" */ "@/views/error/Error.vue"),
  },
  {
    path: "/edit_job",
    name: "Edit Job",
    meta: { title: "Edit Job" },
    props: (route) => ({ jobId: route.query.jobId, token: route.query.token }),
    component: () =>
      import(/* webpackChunkName: "errors-500" */ "@/job/NoTokenEditSheet.vue"),
  },

];

// NOTE: The order in which routes are added to the list matters when evaluated. For example, /jobs/report will take precendence over /jobs/:name.
export const protectedRoute = [
  {
    path: "/",
    component: DefaultLayout,
    meta: { title: "Dispatch", group: "jobs", icon: "" },
    redirect: "/jobs",
    children: [
      {
        path: "/403",
        name: "Forbidden",
        meta: { title: "Access Denied", hiddenInMenu: true },
        component: () =>
          import(/* webpackChunkName: "error-403" */ "@/views/error/Deny.vue"),
      },
    ],
  },
  {
    path: "/jobs/status",
    meta: { title: "Status", icon: "", requiresAuth: true },
    component: () =>
      import(/* webpackChunkName: "jobs-status" */ "@/job/Status.vue"),
  },

  {
    path: "/jobs/report",
    meta: { title: "Report", icon: "", requiresAuth: true },
    component: () =>
      import(/* webpackChunkName: "jobs-report" */ "@/job/ReportForm.vue"),
  },
  {
    path: "/jobs/types",
    component: DefaultLayout,
    meta: {
      title: "Job Types",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true,
    },
  },
  {
    path: "/liveMap",
    component: DefaultLayout,
    meta: {
      title: "liveMap",
      icon: "view_compact",
      group: "dashboard",
      requiresAuth: true,
    },
    children: [
      {
        path: "/liveMap",
        name: "LiveMap",
        component: () =>
          import(
            /* webpackChunkName: "job-dashboard" */ "@/live_map/LiveMap.vue"
          ),
      },
    ],
  },
  {
    path: "/gantt",
    component: DefaultLayout,
    meta: {
      title: "gantt",
      icon: "view_compact",
      group: "gantt",
      requiresAuth: true,
    },
    children: [
      {
        path: "/gantt",
        name: "Gantt",
        component: () =>
          import(/* webpackChunkName: "job-dashboard-gantt" */ "@/gantt/Gantt.vue"),
      },
    ],
  },
  {
    path: "/jobs",
    component: DefaultLayout,
    meta: {
      title: "Jobs",
      icon: "view_compact",
      group: "jobs",
      requiresAuth: true,
    },
    children: [
      {
        path: "/jobs",
        name: "JobTable",
        component: () =>
          import(/* webpackChunkName: "job-table" */ "@/job/Table.vue"),
      },
    ],
  },
  {
    path: "/plan_jobs",
    component: DefaultLayout,
    meta: {
      title: "JobHistory",
      icon: "view_compact",
      group: "JobHistory",
      requiresAuth: true,
    },
    children: [
      {
        path: "/plan_jobs",
        name: "JobHistoryTable",
        component: () =>
          import(/* webpackChunkName: "job-table_plan_jobs" */ "@/plan_jobs/Table.vue"),
      },
    ],
  },  
  {
    path: "/services",
    component: DefaultLayout,
    meta: {
      title: "Services",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true,
    },
    children: [
      {
        path: "/services",
        name: "ServiceTable",
        component: () =>
          import(/* webpackChunkName: "service-table" */ "@/service/Table.vue"),
      },
    ],
  },
  {
    path: "/service_plugin",
    component: DefaultLayout,
    meta: {
      title: "Service Plugins",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true,
    },
    children: [
      {
        path: "/service_plugin",
        name: "ServicePluginTable",
        component: () =>
          import(
            /* webpackChunkName: "service-table-plugin" */ "@/service_plugin/Table.vue"
          ),
      },
    ],
  },
  {
    path: "/workers",
    component: DefaultLayout,
    meta: {
      title: "Workers",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true,
    },
    children: [
      {
        path: "/workers",
        name: "WorkerTable",
        component: () =>
          import(/* webpackChunkName: "worker-table" */ "@/worker/Table.vue"),
      },
    ],
  },
  {
    path: "/teams",
    component: DefaultLayout,
    meta: {
      title: "Teams",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true,
    },
    children: [
      {
        path: "/teams",
        name: "TeamTable",
        component: () =>
          import(/* webpackChunkName: "team-table" */ "@/team/Table.vue"),
      },
    ],
  },
  {
    path: "/items",
    component: DefaultLayout,
    meta: {
      title: "Items",
      icon: "view_compact",
      group: "inventory",
      requiresAuth: true,
    },
    children: [
      {
        path: "/items",
        name: "ItemTable",
        component: () =>
          import(/* webpackChunkName: "item-table" */ "@/item/Table.vue"),
      },
    ],
  },
  {
    path: "/depots",
    component: DefaultLayout,
    meta: {
      title: "Depots",
      icon: "view_compact",
      group: "inventory",
      requiresAuth: true,
    },
    children: [
      {
        path: "/depots",
        name: "DepotsTable",
        component: () =>
          import(/* webpackChunkName: "depot-table" */ "@/depot/Table.vue"),
      },
    ],
  },
  {
    path: "/item_inventory",
    component: DefaultLayout,
    meta: {
      title: "ItemsInventory",
      icon: "view_compact",
      group: "inventory",
      requiresAuth: true,
    },
    children: [
      {
        path: "/item_inventory",
        name: "ItemInventoryTable",
        component: () =>
          import(
            /* webpackChunkName: "inventory-table" */ "@/item_inventory/Table.vue"
          ),
      },
    ],
  },
  {
    path: "/tags",
    component: DefaultLayout,
    meta: {
      title: "Tags",
      icon: "view_compact",
      group: "contacts",
      requiresAuth: true,
    },
    children: [
      {
        path: "/tags",
        name: "TagTable",
        component: () =>
          import(/* webpackChunkName: "tag-table" */ "@/tag/Table.vue"),
      },
    ],
  },
  {
    path: "/search",
    component: DefaultLayout,
    meta: {
      title: "Search",
      icon: "view_compact",
      group: "search",
      requiresAuth: true,
    },
    children: [
      {
        path: "/search",
        name: "ResultList",
        component: () =>
          import(
            /* webpackChunkName: "search-result-list" */ "@/search/ResultList.vue"
          ),
      },
    ],
  },
  {
    path: "/plugins",
    component: DefaultLayout,
    meta: {
      title: "Plugins",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true,
    },
    children: [
      {
        path: "/plugins",
        name: "PluginTable",
        component: () =>
          import( "@/plugin/Table.vue"),
      },
    ],
  },
  {
    path: "/locations",
    component: DefaultLayout,
    meta: {
      title: "Locations",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true,
    },
    children: [
      {
        path: "/locations",
        name: "LocationTable",
        component: () =>
          import(
             "@/location/Table.vue"
          ),
      },
    ],
  },
  {
    path: "/users",
    component: DefaultLayout,
    meta: {
      title: "Users",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true,
    },
    children: [
      {
        path: "/users",
        name: "UserTable",
        component: () =>
          import( "@/auth/Table.vue"),
      },
    ],
  },
  {
    path: "/organization",
    component: DefaultLayout,
    meta: {
      title: "Organization",
      icon: "view_compact",
      group: "configuration",
      requiresAuth: true,
    },
    children: [
      {
        path: "/organization",
        name: "OrganizationTable",
        component: () =>
          import( "@/org/Table.vue"),
      },
    ],
  },
];
