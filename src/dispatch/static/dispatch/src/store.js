import Vue from "vue";
import Vuex from "vuex";

import app from "@/app/store";
import job from "@/job/store";
import worker from "@/worker/store";
import search from "@/search/store";
import service from "@/service/store";
import team from "@/team/store";
import auth from "@/auth/store";
import tag from "@/tag/store";
import plugin from "@/plugin/store";
import gantt from "@/gantt/store";
import location from "@/location/store";
import item from "@/item/store";
import depot from "@/depot/store";
import item_inventory from "@/item_inventory/store";
import service_plugin from "@/service_plugin/store";
import live_map from "@/live_map/store";
import org from "@/org/store";
import plan_jobs from "@/plan_jobs/store";

Vue.use(Vuex);

export default new Vuex.Store({
  modules: {
    app,
    auth,
    tag,
    job,
    worker,
    plugin,
    search,
    service,
    team,
    gantt,
    location,
    service_plugin,
    live_map,
    org,
    item,
    depot,
    item_inventory,
    plan_jobs,
  },
  strict: process.env.NODE_ENV !== "production",
});
