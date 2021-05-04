const Menu = [
  { header: "Dashboard" },
  {
    title: "Planner Chart",
    group: "gantt",
    component: "Gantt",
    icon: "mdi-chart-timeline",
    href: "/gantt"
  },
  { header: "Jobs" },

  {
    title: "Jobs",
    group: "jobs",
    component: "Jobs",
    icon: "star",
    href: "/jobs"
  },
  {
    title: "Locations",
    group: "Configuration",
    name: "Locations",
    icon: "place",
    href: "/locations"
  },

  { header: "Workers" },
  {
    title: "Workers",
    group: "workers",
    icon: "person",
    href: "/workers",
    name: "Worker"
  },
  {
    title: "Team",
    group: "workers",
    name: "Team",
    icon: "people",
    href: "/teams"
  },
  { header: "Configuration" },

  {
    title: "Planner Service",
    group: "Configuration",
    name: "Service",
    icon: "room_service",
    href: "/services"
  },
  {
    title: "Service & Plugins",
    group: "Configuration",
    name: "Service_Plugin",
    icon: "link",
    href: "/service_plugin"
  },
  {
    title: "Plugins",
    group: "Configuration",
    name: "Plugins",
    icon: "power",
    href: "/plugins"
  }
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
Menu.forEach(item => {
  if (item.items) {
    item.items.sort((x, y) => {
      let textA = x.job_code.toUpperCase();
      let textB = y.job_code.toUpperCase();
      return textA < textB ? -1 : textA > textB ? 1 : 0;
    });
  }
});

export default Menu;
