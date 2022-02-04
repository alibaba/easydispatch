const Menu = [
  {
    header: "Dashboard",
    visibleRoles:["Owner","Planner"],
  },
  {
    title: "Live Map",
    group: "dashboard",
    component: "LiveMap",
    icon: "mdi-map",
    href: "/liveMap",
    visibleRoles:["Owner","Planner"],
  },
  {
    title: "Planner Chart",
    group: "gantt",
    component: "Gantt",
    icon: "mdi-chart-timeline",
    href: "/gantt",
    visibleRoles:["Owner","Planner"],
  },

  // {
  //   title: "JobHistory",
  //   group: "jobs",
  //   name: "JobHistory",
  //   icon: "mdi-clock-check-outline",
  //   href: "/plan_jobs",
  // },
  {
    header: "Jobs",
    visibleRoles:["Owner","Planner"],
  },

  {
    title: "All Jobs",
    group: "jobs",
    component: "Jobs",
    icon: "star",
    href: "/jobs",
    visibleRoles:["Owner","Planner", ],
  },  
  {
    title: "My Jobs",
    group: "jobs",
    component: "MyJobs",
    icon: "star",
    href: "/job_table_4_worker",
    visibleRoles:[ "Worker", ],
  },
  {
    title: "My Current",
    group: "jobs",
    component: "MyJobs",
    icon: "mdi-console-network",
    href: "/job_table_4_worker_current",
    visibleRoles:[ "Worker", ],
  },
  {
    title: "My Finished",
    group: "jobs",
    component: "MyFinished",
    icon: "mdi-check-network-outline",
    href: "/job_table_4_worker_finished",
    visibleRoles:[ "Worker"],
  },

  {
    title: "Locations",
    group: "Configuration",
    name: "Locations",
    icon: "place",
    href: "/locations",
    visibleRoles:["Owner","Customer"],
  },
  {
    title: "My Jobs",
    group: "jobs",
    component: "MyJobs",
    icon: "star",
    href: "/job_table_4_customer",
    visibleRoles:[ "Customer",  ],
  },

  { header: "Workers" },
  {
    title: "Workers",
    group: "workers",
    icon: "person",
    href: "/workers",
    name: "Worker",
  },
  {
    title: "Team",
    group: "workers",
    name: "Team",
    icon: "people",
    href: "/teams",
  },
  { header: "Inventory" },
  {
    title: "Items",
    group: "Inventory",
    name: "Item",
    icon: "mdi-toy-brick-outline",
    href: "/items",
  },
  {
    title: "Depots",
    group: "Inventory",
    name: "Depot",
    icon: "mdi-home-circle-outline",
    href: "/depots",
  },
  {
    title: "Inventory",
    group: "Inventory",
    name: "ItemInventory",
    icon: "mdi-home-search-outline",
    href: "/item_inventory",
  },
  {
    header: "Configuration",
    visibleRoles:["Owner",],
  },
  {
    title: "Planner Service",
    group: "Configuration",
    name: "Service",
    icon: "room_service",
    href: "/services",
    visibleRoles:["Owner",],
  },
  {
    title: "Plugins in Services",
    group: "Configuration",
    name: "Service_Plugin",
    icon: "link",
    href: "/service_plugin",
    visibleRoles:["Owner",],
  },
  {
    title: "Plugins",
    group: "Configuration",
    name: "Plugins",
    icon: "power",
    href: "/plugins",
    visibleRoles:["Owner",],
  },
  {
    title: "Login Accounts",
    group: "Configuration",
    name: "Users",
    icon: "account_box",
    href: "/users",
    visibleRoles:["Owner",],
  },
  {
    title: "Setting",
    group: "Configuration",
    name: "Organization",
    icon: "mdi-cog-outline",
    href: "/organization",
    visibleRoles:["Owner",],
  },
  // {
  //   title: "Login Accounts",
  //   group: "Configuration",
  //   name: "Users",
  //   icon: "account_box",
  //   href: "/users"
  // },
  // {
  //   title: "Tags",
  //   group: "Configuration",
  //   name: "Tags",
  //   icon: "label",
  //   href: "/Tags"
  // },
];
// reorder menu
Menu.forEach((item) => {
  if (item.items) {
    item.items.sort((x, y) => {
      let textA = x.job_code.toUpperCase();
      let textB = y.job_code.toUpperCase();
      return textA < textB ? -1 : textA > textB ? 1 : 0;
    });
  }
});

export default Menu;
