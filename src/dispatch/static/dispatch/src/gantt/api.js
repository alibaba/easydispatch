import API from "@/api";

const resource = "/services";
const planner_resource = "/planner_service";

export default {
  getPlannerWorkerJobDataset(options) {
    return API.get(`${planner_resource}/get_planner_worker_job_dataset/`, {
      params: { ...options },
    });
  },
  getPlannerScoreStats(options) {
    return API.get(`${planner_resource}/get_planner_score_stats/`, {
      params: { ...options },
    });
  },

  doSingleJobDropCheck(options) {
    return API.post(`${planner_resource}/single_job_drop_check/`, {
      ...options,
    });
  },
  getRecommendedSlots(options) {
    return API.post(`${planner_resource}/generic_job_predict_actions/`, {
      ...options,
    });
  },
  commitJobAction(options) {
    return API.post(`${planner_resource}/generic_job_commit/`, { ...options });
  },
  resetPlanningWindow(options) {
    return API.post(`${planner_resource}/reset_planning_window/`, {
      ...options,
    });
  },
  runBatchOptimizer(options) {
    return API.post(`${planner_resource}/run_batch_optimizer/`, {
      ...options,
    });
  },
  get(termId) {
    return API.get(`${resource}/${termId}`);
  },

  create(payload) {
    return API.post(`${resource}/`, payload);
  },

  update(termId, payload) {
    return API.put(`${resource}/${termId}`, payload);
  },

  delete(termId) {
    return API.delete(`${resource}/${termId}`);
  },
};
