<template>
  <div :class="className" :style="{ height: chartDivHeight, width: width }" />
</template>

<script>
import echarts from "echarts";
require("echarts/theme/macarons"); // echarts theme
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import resize from "./mixins/resize";
import formatISO from "date-fns/formatISO";
//import GanttApi from "@/gantt/api"
// singleJobDropCheckAPI

var HEIGHT_RATIO = 0.6;
var POS_JOB_INDEX_worker_index = 0;
var POS_JOB_INDEX_start_datetime = 1;
var POS_JOB_INDEX_end_datetime = 2;
var POS_JOB_INDEX_job_code = 3 + 0;
var POS_JOB_INDEX_job_type = 4 + 0;
var POS_JOB_INDEX_travel_minutes_before = 5 + 0;
var POS_JOB_INDEX_travel_prev_code = 6 + 0;
var POS_JOB_INDEX_conflict_level = 7 + 0;
var POS_JOB_INDEX_worker_code = 8;
// var POS_JOB_INDEX_geo_longitude = 9 + 0
// var POS_JOB_INDEX_geo_latitude = 10 + 0
var POS_JOB_INDEX_changed_flag = 11 + 0;
var POS_JOB_INDEX_prev_geo_longitude = 12 + 0;
var POS_JOB_INDEX_prev_geo_latitude = 13 + 0;
var POS_JOB_INDEX_prev_location_type = 14 + 0;

var POS_WORKER_INDEX_worker_index = 0;
var POS_WORKER_INDEX_skills = 1 + 0;
// var POS_WORKER_INDEX_max_conflict_level = 2 + 0
var POS_WORKER_INDEX_worker_code = 3;
//var POS_WORKER_INDEX_geo_longitude = 4 + 0
//var POS_WORKER_INDEX_geo_latitude = 5 + 0
var POS_WORKER_INDEX_weekly_working_minutes = 6 + 0;

var POS_WORKER_INDEX_selected = 7;
var POS_WORKER_INDEX_name = 8;

var POS_WORKING_TIME_INDEX_worker_index = 0;
var POS_WORKING_TIME_INDEX_start_ms = 1 + 0;
var POS_WORKING_TIME_INDEX_end_ms = 2 + 0;
var POS_WORKING_TIME_INDEX_start_overtime = 3 + 0;
var POS_WORKING_TIME_INDEX_end_overtime = 4 + 0;

// I picked up colors from here:
// https://www.w3schools.com/colors/colors_names.asp

var job_types = {
  appt: { name: "Appointment", color: "#FF8C00", zlevel: 200 }, //#ff0000
  event: { name: "Diary Event", color: "#d9d9d9", zlevel: 5 },
  P: { name: "Planned", color: "#7b9ce1", zlevel: 20 },
  I: { name: "Inplanning", color: "#72b362", zlevel: 10 },
  // U: { name: "Unplanned-new", color: "#e0bc78", zlevel: 10 },
  // others: { name: "others", color: "#D2A8A8", zlevel: 50 },
  // FS: { name: "Fixed Schedule", color: "#7b9ce1", zlevel: 10 },
  // FD: { name: "Fixed Day", color: "rgb(111, 160, 199)", zlevel: 10 },
  // FT: { name: "Fixed Time", color: "rgb(111, 160, 160)", zlevel: 10 },
  // N: { name: "Normal", color: "#72b362", zlevel: 10 },
  // NN: { name: "Night Service", color: "#ffff00", zlevel: 10 },
  // NA: { name: "Need Appointment", color: "#e0bc78", zlevel: 10 },
  // CFLT: { name: "Conflicted", color: "#ff0000", zlevel: 100 }, // #bd6d6c
  NEW: { name: "New-Not saved", color: "#dc77dc", zlevel: 200 }, // #bd6d6c
  //'nan': { name: 'Unknown', color: '#D2A8A8' },
};
var dropJobStyleDict = {
  OK: {
    lineWidth: 2,
    fill: "rgba(0,255,0,0.1)",
    stroke: "rgba(0,255,0,0.8)",
    lineDash: [6, 3],
  },
  Warning: {
    lineWidth: 2,
    fill: "rgba(255, 193, 7, 0.3)",
    stroke: "rgba(255, 193, 7, 0.9)",
    lineDash: [6, 3],
  },
  Error: {
    lineWidth: 2,
    fill: "rgba(255,0,0,0.5)",
    stroke: "rgba(255,0,0,1)",
    lineDash: [6, 3],
  },
};
/*
 */

function getNodeItemStyle(jobType, conflict_level) {
  //var jobType = job[POS_JOB_INDEX_job_type]
  //var conflict_level = job[POS_JOB_INDEX_conflict_level]

  var jobServiceType = jobType.split("_")[0];
  if (!(jobServiceType in job_types)) {
    console.log("unknown type:", jobServiceType, jobType);
    jobServiceType = "I";
  }
  var sharedStatus = jobType.split("_")[5];
  var node_color = job_types[jobServiceType]["color"];
  var node_itemStyle = {
    normal: {
      color: node_color,
      borderWidth: 1,
      borderColor: node_color,
      opacity: 0.6,
    },
  };

  if (conflict_level > 0) {
    node_itemStyle = {
      normal: {
        color: node_color,
        borderWidth: 1,
        borderColor: job_types["CFLT"]["color"],
        opacity: 0.6,
        borderType: "solid",
      },
    };
  }

  if (sharedStatus != "N") {
    if (sharedStatus == "P") {
      node_itemStyle.normal.borderColor = "#000000";
      node_itemStyle.normal.borderWidth = 3;
      node_itemStyle.normal.opacity = 1;
    } else if (sharedStatus == "S") {
      node_itemStyle.normal.borderWidth = 1;
      node_itemStyle.normal.borderColor = "#dc77dc";
      node_itemStyle.normal.borderType = "dashed";
    } else {
      console.log("Unkown sharedStatus code", sharedStatus);
    }
  }

  return node_itemStyle;
}

function renderWorker(params, api) {
  var workerIndex = api.value(POS_WORKER_INDEX_worker_index);
  var y = api.coord([0, workerIndex - 0.45])[1];
  if (y < params.coordSys.y + 3) {
    return;
  }
  var selectedIndicator = api.value(POS_WORKER_INDEX_selected);
  var selectedFill = "#7b9ce1"; // 72b362 , reused for paired.
  if (selectedIndicator == 0) {
    selectedFill = "#368c6c";
  }
  return {
    type: "group",
    position: [10, y],
    children: [
      {
        type: "rect",
        shape: {
          x: 0,
          y: -23,
          width: 90,
          height: 20,
        },
        style: {
          fill: selectedFill,
        },
      },
      {
        type: "text",
        style: {
          x: 40,
          y: -6,
          text: api.value(POS_WORKER_INDEX_name),
          textVerticalAlign: "bottom",
          textAlign: "center",
          textFill: "#fff",
        },
      },
    ],
  };
}

function renderWorkerSplitLine(params, api) {
  var workerIndex = api.value(POS_WORKER_INDEX_worker_index);

  //var x_max = myChart.getModel().getComponent('xAxis').axis.extent

  var y = api.coord([0, workerIndex + HEIGHT_RATIO - 0.1])[1];
  if (y < params.coordSys.y + 3) {
    return;
  }

  return {
    type: "group",
    children: [
      {
        type: "line",
        shape: {
          x1: params.coordSys.x,
          y1: y,
          x2: params.coordSys.x + params.coordSys.width,
          y2: y,
        },

        style: {
          opacity: 0.2,
          stroke: "#008000",
        },
      },
      {
        type: "rect",
        shape: {
          x: params.coordSys.x + 100,
          y: y,
          width: 0,
          height: 10,
        },
        style: {
          normal: {
            color: "#fff",
            borderWidth: 1,
            borderColor: "rgba(53, 54, 38, 0.3)",
            opacity: 0.6,
            borderType: "dashed",
          },
        },
      },
    ],
  };
}

function renderWorkingTime(params, api) {
  //console.log(api.value(0), api.value(1), api.value(2)) // worker, start, end
  var workerIndex = api.value(POS_WORKING_TIME_INDEX_worker_index);
  var jobStartTimeMS = api.value(POS_WORKING_TIME_INDEX_start_ms);
  var jobEndTimeMS = api.value(POS_WORKING_TIME_INDEX_end_ms);

  var jobStartOverTimeMS =
    jobStartTimeMS - api.value(POS_WORKING_TIME_INDEX_start_overtime);
  var jobEndOverTimeMS =
    jobEndTimeMS + api.value(POS_WORKING_TIME_INDEX_end_overtime);

  var start = api.coord([jobStartTimeMS, workerIndex]);
  var end = api.coord([jobEndTimeMS, workerIndex]);

  var worker_timeline_height = api.size([0, 1])[1];
  var height = worker_timeline_height * 0.05;
  if (height < 3) {
    height = 3;
  }

  //var start_y = (api.size([0, 1])[1] * 0);

  let new_style = api.style();
  let overtime_style = Object.assign({}, new_style);
  overtime_style.fill = "Red";

  var rectShape = echarts.graphic.clipRectByRect(
    {
      x: start[0],
      y: start[1] - worker_timeline_height * 0.5 - 1, //- 1 to overwrite the normal dashed splitline
      width: end[0] - start[0],
      height: height,
    },
    {
      x: params.coordSys.x,
      y: params.coordSys.y,
      width: params.coordSys.width,
      height: params.coordSys.height,
    }
  );
  var workingSlotShapeGroup = {
    type: "group",
    children: [
      {
        type: "rect",
        shape: rectShape,
        style: new_style,
      },
    ],
  };

  if (jobStartOverTimeMS < jobStartTimeMS) {
    var overtimeStartCoordinate = api.coord([jobStartOverTimeMS, workerIndex]);
    var startOvertimeShape = echarts.graphic.clipRectByRect(
      {
        x: overtimeStartCoordinate[0],
        y: start[1] - worker_timeline_height * 0.5 - 1, //- 1 to overwrite the normal dashed splitline
        width: start[0] - overtimeStartCoordinate[0],
        height: height,
      },
      {
        x: params.coordSys.x,
        y: params.coordSys.y,
        width: params.coordSys.width,
        height: params.coordSys.height,
      }
    );
    workingSlotShapeGroup.children.push({
      type: "rect",
      shape: startOvertimeShape,
      style: overtime_style,
    });
  }
  if (jobEndOverTimeMS > jobEndTimeMS) {
    var overtimeEndCoordinate = api.coord([jobEndOverTimeMS, workerIndex]);
    var endOvertimeShape = echarts.graphic.clipRectByRect(
      {
        x: end[0],
        y: start[1] - worker_timeline_height * 0.5 - 1, //- 1 to overwrite the normal dashed splitline
        width: overtimeEndCoordinate[0] - end[0],
        height: height,
      },
      {
        x: params.coordSys.x,
        y: params.coordSys.y,
        width: params.coordSys.width,
        height: params.coordSys.height,
      }
    );
    workingSlotShapeGroup.children.push({
      type: "rect",
      shape: endOvertimeShape,
      style: overtime_style,
    });
  }

  return workingSlotShapeGroup;
}

// ----------------------------------------------------
// -- Kandbox Time Utilities
// ----------------------------------------------------
// var global_dataStartTime = null
function lpad(num, size) {
  var s = num + "";
  while (s.length < size) s = "0" + s;
  return s;
}

function date_formatter_hhmm(val) {
  //console.log("axis", new Date(val) )
  var vdate = new Date(val);

  // let intMinutes = Math.floor(vdate - global_dataStartTime) / 1000 / 60

  var texts = [
    lpad(vdate.getHours(), 2),
    lpad(vdate.getMinutes(), 2),
    // parseInt(intMinutes) //vdate.getHours() * 60 + vdate.getMinutes()
  ];
  return texts.join(":");
}

function date_formatter_mmdd_hhmm(val) {
  //console.log("axis", new Date(val) )
  let vdate = new Date(val);
  let mmdd = [vdate.getMonth() + 1, vdate.getDate()].join("-");
  // hhmm = vdate.toTimeString().split(' ')[0];
  var minute = "" + vdate.getMinutes();
  if (minute.length < 2) minute = "0" + minute;
  var hour = "" + vdate.getHours();
  if (hour.length < 2) hour = "0" + hour;
  let hhmm = hour + ":" + minute;
  return mmdd + " " + hhmm; //
}

// ----------------------------------------------------
// --  Enable Dragging
// ----------------------------------------------------

var _draggingEl;
var _dropShadow;
var _draggingCursorOffset = [0, 0];
var _draggingTimeLength;
var _draggingRecord;
var _dropRecord;
//var _cartesianXBounds = []
//ar _cartesianYBounds = []

var _single_job_drop_check_ajay_lock = false;

// ----------------------------------------------------
// -- Start Vue
// ----------------------------------------------------

export default {
  name: "JobsTimelineChart",

  mixins: [resize],
  props: {
    className: {
      type: String,
      default: "chart",
    },
    width: {
      type: String,
      default: "100%",
    } /*
    height: {
      type: String,
      default: "650px"
    },*/,
    autoResize: {
      type: Boolean,
      default: true,
    },
  },
  data() {
    return {
      chart: null,
      //chartHeight: 200,
      chartDivHeight: "200px",
      //dataStartTime:null
    };
  },
  computed: {
    ...mapFields("gantt", [
      //"INDEX_CONFIG",
      "global_loaded_data",
      "global_job_dict",
      "selectedWorkerList",
      "chartClickBehaviour",
      "latLongRouteArray",
      "singleJobDropCheckResult",
      "singleJobDropCheckOptions",
      "plannerFilters",
      "planned_jobs_data_last_upate_date_string",
      "chartDraggable",
      "chartClickShowMapFlag",
    ]),
  },

  watch: {
    chartDraggable(newValue) {
      console.log(`chartDraggable is changed to ${newValue}`);
      if (newValue) {
        this.initDrag(
          this.chart,
          this.global_loaded_data,
          this.global_job_dict,
          this.plannerFilters
        );
      }
    },
    global_loaded_data(newValue) {
      // https://dev.to/viniciuskneves/watch-for-vuex-state-changes-2mgj
      console.log(`global_loaded_data: Updating chart`);
      // console.log(newValue)
      this.drawJobTimelineChart(newValue);
      this.initDrag(
        this.chart,
        newValue,
        this.global_job_dict,
        this.plannerFilters
      );
    },
    planned_jobs_data_last_upate_date_string: {
      //deep: true,
      handler(newValue, oldValue) {
        //newValue, oldValue
        console.log(
          `planned_jobs_data_last_upate_date_string changed because of  jobs_data change, (old): ${oldValue} to (new:) ${newValue} , and now data len is ${this.global_loaded_data.planned_jobs_data.length}`
        );
        this.drawJobTimelineChart(this.global_loaded_data);
        this.initDrag(
          this.chart,
          this.global_loaded_data,
          this.global_job_dict,
          this.plannerFilters
        );
      },
      // immediate: true,
    },

    chartClickBehaviour(newValue, oldValue) {
      console.log(
        `changed chartClickBehaviour from ${oldValue} to ${newValue}`
      );
      //return
      //
      this.setChartClickBehavior(newValue);
    },
    singleJobDropCheckResult(newValue) {
      // console.log(`changed singleJobDropCheckResult from ${oldValue} to ${newValue}`)
      //return   , oldValue
      //
      this.on_success_single_job_drop_check(newValue);
    },
  },
  mounted() {
    this.$nextTick(() => {
      this.initChart();
    });
  },
  beforeDestroy() {
    if (!this.chart) {
      return;
    }
    this.chart.dispose();
    this.chart = null;
  },
  methods: {
    ...mapActions("gantt", [
      "showDialogMapRoute",
      "doSingleJobDropCheck",
      "showActionWithRecommendation",
    ]),
    initChart() {
      // this.chart = echarts.init(this.$el, "macarons")
      // this.setOptions(this.chartData)
      console.log(this.global_loaded_data);
      this.chart = echarts.init(this.$el, null, { renderer: "svg" });
      this.drawJobTimelineChart(this.global_loaded_data);
      this.initDrag(
        this.chart,
        this.global_loaded_data,
        this.global_job_dict,
        this.plannerFilters
      );
      if (this.chartDraggable) {
        this.setChartClickBehavior("drag_n_drop");
      } else {
        if (this.chartClickShowMapFlag) {
          this.setChartClickBehavior("check_map");
        } else {
          this.setChartClickBehavior("show_job");
        }
      }
    },
    setChartClickBehavior(dragBehaviorCode) {
      this.chart.off("click");
      if (dragBehaviorCode == "drag_n_drop") {
        // this.chartDraggable = true
      } else {
        // this.chart.on("click", onJobTimelineChartClick_all)
        if (dragBehaviorCode == "check_map") {
          this.chart.on("click", this.onChartClick_ShowMap);
        } else {
          //  (dragBehaviorCode == 'show_job')
          console.log("default chartClickBehaviour as show_job");
          this.chart.on("click", this.onChartClick_ShowJobAdmin);
        }
      }
    },
    drawJobTimelineChart(loaded_data) {
      var _that = this;
      // eslint-disable-line no-unused-vars
      // draw_chart
      var categories = [];
      // var timeline_data = []

      // var startTime = new Date('2019-01-01T00:00:00').getTime();
      // var endTime   = startTime + (24*60*60*1000);
      var startTime = new Date(loaded_data["start_time"]).getTime();
      var endTime = new Date(loaded_data["end_time"]).getTime();

      // global_dataStartTime = startTime

      // workers_list = []
      //jobs_list = []

      //console.log(data);
      var workers_data = loaded_data["workers_data"];

      var working_timeslot_data = [];

      //reset global job dict
      //global_worker_dict = {}

      workers_data.forEach(function(w) {
        //for (var key in workers_dict){
        //console.log( key, workers_dict[key] );
        // w.splice(POS_INDEX_node_type, 0, VALUE_WORKER_INDEX_node_type);
        //w[POS_WORKER_INDEX_node_type] = VALUE_WORKER_INDEX_node_type
        let worker_index = w[POS_WORKER_INDEX_worker_index];

        //global_worker_dict[w[POS_WORKER_INDEX_worker_code]] = worker_index

        // TODO, temporyary disable 2021-01-21 09:24:15
        // if (_that.selectedWorkerList.includes(worker_index)) {
        //   w[POS_WORKER_INDEX_selected] = 1
        // } else {
        //   w[POS_WORKER_INDEX_selected] = 0
        // }

        categories.push(worker_index);

        let currentDate = new Date(loaded_data["start_time"]);
        let dataStartDate = new Date(loaded_data["start_time"]);
        let day_seq = 0;
        while (day_seq < w[POS_WORKER_INDEX_weekly_working_minutes].length) {
          // let weekDayIndex = currentDate.getDay()
          let day_timeslot =
            w[POS_WORKER_INDEX_weekly_working_minutes][day_seq]; //JSON.parse(
          working_timeslot_data.push([
            worker_index,
            dataStartDate.getTime() + day_timeslot[0] * 60000,
            dataStartDate.getTime() + day_timeslot[1] * 60000,
            day_timeslot[2] * 60000,
            day_timeslot[3] * 60000,
          ]);
          //console.log(currentDate, weekDayIndex)
          currentDate.setDate(currentDate.getDate() + 1); // 1 2020-10-20 18:57:26, now the timeslot already contained 1440*day_i
          day_seq = day_seq + 1;
        }
        //console.log('loaded worker data: ', working_timeslot_data)
      });

      let planned_jobs_data = loaded_data["planned_jobs_data"];
      if (planned_jobs_data.length < 1) {
        console.log("No planned jobs are found!");
        //Do not return, I still draw workers.
      }
      //planned_jobs_data
      //reset global job dict

      _that.global_job_dict = {};
      loaded_data["all_jobs_in_env"].forEach(function(job, index) {
        _that.global_job_dict[job.job_code] = {
          data_latlng: [job.geo_latitude, job.geo_longitude],
          job_index_in_all: index,
        };

        //var jobType = job[POS_JOB_INDEX_job_type]
        // var jobServiceType = itemTypeStr.split("_")[0];
        //var conflict_level = job[POS_JOB_INDEX_conflict_level] // eslint-disable-line no-unused-vars
        // let jobType = job[POS_JOB_INDEX_job_type]
        // let conflict_level = job[POS_JOB_INDEX_conflict_level]

        // let node_itemStyle = getNodeItemStyle(jobType, conflict_level) //Type, conflict_level
        // _that.global_job_dict[job[POS_JOB_INDEX_job_code]]["node_item_style"] = node_itemStyle
      });

      planned_jobs_data.forEach(function(job, index) {
        if (!(job[POS_JOB_INDEX_job_code] in _that.global_job_dict)) {
          let primaryJobCode = job[POS_JOB_INDEX_job_code].split("_")[0];
          // console.log(job[POS_JOB_INDEX_job_code], job, _that.global_job_dict[primaryJobCode])
          if (
            _that.global_job_dict[primaryJobCode] == null ||
            _that.global_job_dict[primaryJobCode] === undefined
          ) {
            console.log(
              "Skipping one job, primaryJobCode in global_job_dict is not defined: ",
              job[POS_JOB_INDEX_job_code],
              job,
              _that.global_job_dict[primaryJobCode]
            );
            return;
          }

          _that.global_job_dict[job[POS_JOB_INDEX_job_code]] = {
            data_latlng: _that.global_job_dict[primaryJobCode].data_latlng,
            job_index_in_all:
              _that.global_job_dict[primaryJobCode].job_index_in_all,
            job_index_in_planned: index,
          };
        } else {
          _that.global_job_dict[
            job[POS_JOB_INDEX_job_code]
          ].job_index_in_planned = index;
        }
      });

      // 使用刚指定的配置项和数据显示图表。
      // console.log("show list of workers: ", categories)
      let chartHeight = 400;
      if (categories.length > 100) {
        // 密集模式
        chartHeight = categories.length * 20;
      } else if (categories.length > 3) {
        chartHeight = categories.length * 30;
      } else {
        chartHeight = 200;
      }
      // let chartHeight = this.chartHeight //3 * 40

      this.chartDivHeight = chartHeight + 150 + "px";
      this.chart.resize({ height: this.chartDivHeight });
      // https://echarts.apache.org/en/option.html#series-custom.dimensions
      this.global_loaded_data.jobs_dimensions[3] = {
        name: "job_code",
        type: "ordinal",
      };

      var local_option = {
        tooltip: {
          enterable: true,
          hideDelay: 800,
          formatter: function(params) {
            // console.log(params.seriesId)
            var jobInfo;
            var tooltip_str;
            let slotInfo = null;
            //console.log("tooltip: ", params.seriesId)

            switch (params.seriesId) {
              case "jobsSeries":
                let local_start = new Date(
                  params.value[POS_JOB_INDEX_start_datetime]
                ).getTime();
                let local_end = new Date(
                  params.value[POS_JOB_INDEX_end_datetime]
                ).getTime();

                jobInfo = 
                  params.marker + "Job: " +
                  params.value[POS_JOB_INDEX_job_code] +
                  "( " +
                  params.value[POS_JOB_INDEX_worker_code] +
                  ", time: " +
                  date_formatter_hhmm(local_start) +
                  "-" +
                  date_formatter_hhmm(local_end) +
                  " , travel: " +
                  Math.ceil(
                    parseFloat(
                      params.value[POS_JOB_INDEX_travel_minutes_before]
                    )
                  ) +
                  " min)";

                tooltip_str = [
                  '<div contenteditable="true">',
                  // '<button onclick="console.log(\'click\');">click me</button>',
                  jobInfo,
                  "</div>",
                ].join(" ");

                return tooltip_str;
              //break
              case "workersSeries":
                //console.log(params)
                jobInfo = params.marker + "Worker: " +
                  params.value[POS_WORKER_INDEX_name] +
                  `, Skills =(${params.value[
                    POS_WORKER_INDEX_skills
                  ].toString()})`;

                tooltip_str = [
                  '<div contenteditable="true">',
                  jobInfo,
                  "</div>",
                ].join(" ");
                return tooltip_str;
              //break
              case "workingTimeSeries":
                //console.log(params)
                slotInfo =
                  params.marker +
                  `(-${parseInt(
                    params.value[3] / 60000
                  )}) ${date_formatter_hhmm(
                    params.value[1]
                  )}->${date_formatter_hhmm(params.value[2])} (+${parseInt(
                    params.value[4] / 60000
                  )})`;

                return slotInfo;
              //break
              default:
                return null;
            }
          },
          extraCssText: "width:500px; white-space:pre-wrap",
        },
        grid: {
          height: chartHeight + 10 + "px",
          //width: ( window.innerWidth - 100) +'px'
          show: true,
          top: 30,
          bottom: 60,
          left: 100,
          right: 20,
          backgroundColor: "#fff",
          borderWidth: 0,
        },

        dataZoom: [
          {
            type: "slider",
            filterMode: "weakFilter",
            showDataShadow: false,
            top: chartHeight + 100,
            height: 10,
            borderColor: "transparent",
            backgroundColor: "#e2e2e2",
            handleIcon:
              "M10.7,11.9H9.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4h1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7v-1.2h6.6z M13.3,22H6.7v-1.2h6.6z M13.3,19.6H6.7v-1.2h6.6z", // jshint ignore:line
            handleSize: 20,
            handleStyle: {
              shadowBlur: 6,
              shadowOffsetX: 1,
              shadowOffsetY: 2,
              shadowColor: "#aaa",
            },
            labelFormatter: "",
          },
          /*{
                       type: 'inside',
                       filterMode: 'weakFilter',
                       zoomOnMouseWheel: false,
                       moveOnMouseMove: false
                   }*/
        ],
        xAxis: {
          min: startTime,
          max: endTime,
          type: "time",
          axisLine: { show: false },
          scale: true,
          axisLabel: {
            formatter: date_formatter_mmdd_hhmm,
          },
        },
        yAxis: {
          // https://github.com/apache/incubator-echarts/issues/2943
          // silent: false, //does not work! 2020-03-16 08:57:26
          axisTick: { show: false },
          axisLine: { show: false },
          axisLabel: { show: false },
          min: -1,
          max: this.global_loaded_data.workers_data.length,
          splitLine: {
            show: false,
            interval: 0,
            lineStyle: {
              color: ["rgba(53, 54, 38, 0.3)"],
              type: "dashed",
            },
          },

          /*
                type: 'category',
            data: categories,
            axisLine: { show: true },
            //https://github.com/apache/incubator-echarts/issues/3485
            axisLabel: { interval: 0 },
            */
        },
        series: [
          {
            id: "jobsSeries",
            //name: "jobs_boxes",
            type: "custom",
            renderItem: this.renderJob,
            dimensions: this.global_loaded_data.jobs_dimensions,
            itemStyle: {
              normal: {
                opacity: 0.8,
              },
            },
            encode: {
              x: [1, 2],
              y: 0,
            },
            data: this.global_loaded_data.planned_jobs_data, //timeline_data
          },
          {
            //worker
            id: "workersSeries",
            type: "custom",
            renderItem: renderWorker,
            //dimensions: this.global_loaded_data.worker_dimensions,
            encode: {
              x: -1, // Then this series will not controlled by x.
              y: 0,
            },
            data: this.global_loaded_data.workers_data,
          },
          {
            //worker
            id: "workersSplitLineSeries",
            type: "custom",
            renderItem: renderWorkerSplitLine,
            //dimensions: global_loaded_data.worker_dimensions,
            encode: {
              x: -1, // Then this series will not controlled by x.
              y: 0,
            },
            data: echarts.util.map(
              this.global_loaded_data.workers_data,
              function(item, index) {
                return [index].concat(item);
              }
            ),
          },
          {
            //working_timeslot_data
            id: "workingTimeSeries",
            type: "custom",
            renderItem: renderWorkingTime,
            itemStyle: {
              normal: {
                opacity: 0.6,
                color: "#72b362",
                borderWidth: 1,
                borderType: "solid",
              },
            },
            encode: {
              x: [1, 2],
              y: 0,
            },
            data: working_timeslot_data,
          },
        ],
      };

      this.chart.setOption(local_option, true);
      this.setChartClickBehavior("show_job");

      //this.$el.css("height", chartHeight + 200)

      //this.chart.on("click", onJobTimelineChartClick_all)
    },
    renderJob(params, api) {
      /* console.log("plotting job: ", api.value(POS_JOB_INDEX_job_code))
      //console.log(api.value(POS_JOB_INDEX_job_code), api.value(POS_JOB_INDEX_changed_flag));
      //console.log(`api.value(POS_JOB_INDEX_job_code) debug ${api.value(POS_JOB_INDEX_job_code)}`)
      //console.log(api.value(0), api.value(1), api.value(2)) // worker, start, end
      */
      if (api.value(POS_JOB_INDEX_job_code) == "62922_S_52") {
        console.log("api.value(POS_JOB_INDEX_job_code) debug");
      }

      var workerIndex = api.value(POS_JOB_INDEX_worker_index);
      var jobStartTimeMS = new Date(
        api.value(POS_JOB_INDEX_start_datetime)
      ).getTime(); //'2021-05-06T08:00:00'
      var jobEndTimeMS = new Date(
        api.value(POS_JOB_INDEX_end_datetime)
      ).getTime();
      var travelTimeMS =
        api.value(POS_JOB_INDEX_travel_minutes_before) * 1000 * 60;

      let jobType = api.value(POS_JOB_INDEX_job_type);
      var start = api.coord([jobStartTimeMS, workerIndex]);
      var end = api.coord([jobEndTimeMS, workerIndex]);
      //var conflict_level = 0 //api.value(7); //0; //
      let conflict_level = api.value(POS_JOB_INDEX_conflict_level);
      if (workerIndex >= this.global_loaded_data.workers_data.length) {
        console.log(workerIndex, api.value(POS_JOB_INDEX_job_code));
      }
      // var nbr_conflicts =
      //   this.global_loaded_data.workers_data[workerIndex][POS_WORKER_INDEX_max_conflict_level] + 1 //api.value(5) + 1; //1; //

      // api.value(8) -> workerIndex

      var height = api.size([0, 1])[1] * 0.5; // /nbr_conflicts
      var start_y = api.size([0, 1])[1] * 0.2;
      // console.log(conflict_level, nbr_conflicts, height, start_y)

      var travelTimeStartXY = api.coord([
        jobStartTimeMS - travelTimeMS,
        workerIndex,
      ]);
      var travelTime = start[0] - travelTimeStartXY[0];

      if (
        start[0] > params.coordSys.x + params.coordSys.width ||
        start[0] + params.coordSys.width < params.coordSys.x
      ) {
        return;
      }
      if (!(api.value(POS_JOB_INDEX_job_code) in this.global_job_dict)) {
        return;
      }

      var jobServiceType = jobType.split("_")[0];
      //var sharedStatus = jobType.split("_")[5];
      var node_z = job_types[jobServiceType]["zlevel"];

      let new_style = api.style();
      //console.log(`api.value(POS_JOB_INDEX_job_code) debug ${api.value(POS_JOB_INDEX_job_code)}`)

      // let to_add_style = this.global_job_dict[api.value(POS_JOB_INDEX_job_code)]["node_item_style"]
      let to_add_style = getNodeItemStyle(jobType, conflict_level);
      new_style.fill = to_add_style.normal.color;
      new_style.stroke = to_add_style.normal.borderColor;

      var rectShape = echarts.graphic.clipRectByRect(
        {
          x: start[0],
          y: start[1] - start_y + height * conflict_level,
          width: end[0] - start[0],
          height: height,
        },
        {
          x: params.coordSys.x,
          y: params.coordSys.y,
          width: params.coordSys.width,
          height: params.coordSys.height,
        }
      );

      var childRectShape = {
        type: "rect",
        shape: rectShape,
        style: new_style,
      };

      var newJobWhiteRect = null;
      if (api.value(POS_JOB_INDEX_job_code) == "0423-1-N") {
        // pause for debug
        console.log(
          "0423-1-N -- ",
          api.value(POS_JOB_INDEX_job_code),
          api.value(POS_JOB_INDEX_changed_flag)
        );
      }
      if (rectShape) {
        if (api.value(POS_JOB_INDEX_changed_flag) == 1) {
          //&& (jobServiceType != 'EVT')
          // var whiteRectStyle =
          newJobWhiteRect = {
            type: "rect",
            shape: {
              x: rectShape.x + rectShape.width / 4,
              y: rectShape.y + rectShape.height / 4,
              width: rectShape.width / 2,
              height: rectShape.height / 2,
            },
            style: {
              fill: job_types["NEW"]["color"], //'#FFFFFF'
            },
          };
        } else {
          newJobWhiteRect = {
            type: "rect",
            shape: {
              x: rectShape.x + rectShape.width / 4,
              y: rectShape.y + rectShape.height / 4,
              width: rectShape.width / 2,
              height: rectShape.height / 2,
            },
            style: {
              fill: "rgba(255, 255, 255, 0)",
            },
          };
        }
      }
      var jobCodeText = null;
      if (jobServiceType != "EVT") {
        jobCodeText = {
          type: "text",
          style: {
            x: rectShape.x,
            y: rectShape.y + height,
            text: api.value(POS_JOB_INDEX_job_code),
            fontSize: 8,
            textVerticalAlign: "bottom",
            textAlign: "left",
            textFill: "rgba(255, 255, 255, 0.1)",
          },
        };
      }

      //var groupShape = {}
      if (start[0] - travelTime < params.coordSys.x) {
        //This travel time line should be reduced and restricted to xAxis at zero
        var line_end = start[0];
        if (line_end < params.coordSys.x) {
          line_end = params.coordSys.x;
        }
        return {
          type: "group",
          z: node_z,
          children: [
            {
              type: "circle",
              shape: {
                cx: params.coordSys.x,
                cy: start[1] - start_y + height * (conflict_level + 0.5),
                r: height / 6,
              },
              style: new_style,
            },
            {
              type: "line",
              shape: {
                x1: params.coordSys.x,
                y1: start[1] - start_y + height * (conflict_level + 0.5),
                x2: line_end,
                y2: start[1] - start_y + height * (conflict_level + 0.5),
              },
              style: new_style,
            },
            childRectShape,
            newJobWhiteRect,
            jobCodeText,
          ],
        };
      } else {
        //Draws the travel time line and circle to the front of job box
        return {
          type: "group",
          z: node_z,
          children: [
            {
              type: "circle",
              shape: {
                cx: start[0] - travelTime,
                cy: start[1] - start_y + height * (conflict_level + 0.5),
                r: height / 6,
              },
              style: new_style,
            },
            {
              type: "line",
              shape: {
                x1: start[0] - travelTime,
                y1: start[1] - start_y + height * (conflict_level + 0.5),
                x2: start[0],
                y2: start[1] - start_y + height * (conflict_level + 0.5),
              },
              style: new_style,
            },
            childRectShape,
            newJobWhiteRect,
            jobCodeText,
          ],
        };
      }

      //return groupShape;
    },
    onChartClick_ShowMap(params) {
      //console.log("to show job route, from: ", params.value[6], global_job_dict[params.value[6]]['data_latlng'], " to job: ",
      //    params.value[3], global_job_dict[params.value[3]]['data_latlng'] )
      if (params.seriesId == "jobsSeries") {
        if (
          params.value[POS_JOB_INDEX_travel_prev_code] in this.global_job_dict
        ) {
          console.log(
            "Routing path from Job (" +
              params.value[POS_JOB_INDEX_travel_prev_code] +
              ") to (" +
              params.value[POS_JOB_INDEX_job_code] +
              ")"
          ); //params.name
          // TODO  import { forEach } from "lodash"
          for (
            let i = 0;
            i < this.global_loaded_data.all_jobs_in_env.length;
            i++
          ) {
            if (
              this.global_loaded_data.all_jobs_in_env[i].job_code ==
              params.value[POS_JOB_INDEX_job_code]
            ) {
              this.$store.commit("gantt/SET_SELECTED", {
                job: this.global_loaded_data.all_jobs_in_env[i],
              });
              break;
            }
          }

          this.showDialogMapRoute(
            // show_job_route(
            [
              this.global_job_dict[
                params.value[POS_JOB_INDEX_travel_prev_code]
              ]["data_latlng"],
              this.global_job_dict[params.value[POS_JOB_INDEX_job_code]][
                "data_latlng"
              ],
            ]
          );
        } else {
          console.log(
            "Sorry, this visit has no previous visit in the same day, and I am plotting prev loc.",
            "loc type = ",
            params.value[POS_JOB_INDEX_prev_location_type]
          );
          this.showDialogMapRoute([
            [
              params.value[POS_JOB_INDEX_prev_geo_latitude],
              params.value[POS_JOB_INDEX_prev_geo_longitude],
            ],
            this.global_job_dict[params.value[POS_JOB_INDEX_job_code]][
              "data_latlng"
            ],
          ]);
        }
      } else if (params.seriesId == "workersSeries") {
        let workerIndex = params.value[POS_WORKER_INDEX_worker_index];
        let workerCode = params.value[POS_WORKER_INDEX_worker_code];

        let currentWorkerList = this.selectedWorkerList;
        const listWorkerIndex = currentWorkerList.indexOf(workerCode);
        if (listWorkerIndex > -1) {
          // currentWorkerList.includes(worker_code)
          this.global_loaded_data.workers_data[workerIndex][
            POS_WORKER_INDEX_selected
          ] = 0;
          currentWorkerList.splice(listWorkerIndex, 1);
        } else {
          this.global_loaded_data.workers_data[workerIndex][
            POS_WORKER_INDEX_selected
          ] = 1;
          currentWorkerList.splice(listWorkerIndex, 0, workerCode);
        }

        this.chart.setOption({
          series: {
            id: "workersSeries",
            data: this.global_loaded_data.workers_data,
          },
        });
      } else {
        console.log("onChartClick_ShowMap: to dod nothing: ");
      }
    },
    onChartClick_ShowJobAdmin(params) {
      switch (params.seriesId) {
        case "jobsSeries":
          console.log(
            `Showing action form for job: ${params.value[POS_JOB_INDEX_job_code]} `
          );
          this.showActionWithRecommendation(
            this.global_loaded_data.all_jobs_in_env[
              this.global_job_dict[params.value[POS_JOB_INDEX_job_code]]
                .job_index_in_all
            ]
          );

          break;
        case "workersSeries":
          console.log(
            `/kpdata/worker/${params.value[POS_WORKER_INDEX_worker_code]}/change/`
          );
          break;
        default:
          return null;
      }
    },

    on_success_single_job_drop_check(data) {
      this.$store.commit("gantt/SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG", true);
      var myChart = this.chart;
      let flag = data["status_code"];
      let z = 99;

      let travelTimeMS = data["travel_time"] * 60 * 1000;
      var style = dropJobStyleDict[flag];

      console.log("single_job_drop_check result: ", data);

      var pointArrival = myChart.convertToPixel("grid", [
        this.singleJobDropCheckOptions.timeArrival,
        this.singleJobDropCheckOptions.categoryIndex,
      ]);
      var pointDeparture = myChart.convertToPixel("grid", [
        this.singleJobDropCheckOptions.timeDeparture,
        this.singleJobDropCheckOptions.categoryIndex,
      ]);

      var pointArrivalWithTravelTime = myChart.convertToPixel("grid", [
        this.singleJobDropCheckOptions.timeArrival - travelTimeMS,
        this.singleJobDropCheckOptions.categoryIndex,
      ]);
      var travelTime = pointArrival[0] - pointArrivalWithTravelTime[0];

      var barLength = pointDeparture[0] - pointArrival[0];
      var barHeight =
        Math.abs(
          myChart.convertToPixel("grid", [0, 0])[1] -
            myChart.convertToPixel("grid", [0, 1])[1]
        ) * HEIGHT_RATIO;
      if (_dropShadow) {
        myChart.getZr().remove(_dropShadow);
        _dropShadow = null;
      }
      /*
       */

      _dropShadow = new echarts.graphic.Group();

      let jobRect = new echarts.graphic.Rect({
        shape: {
          x: pointArrival[0],
          y: pointArrival[1] - barHeight + barHeight / 2,
          width: barLength,
          height: barHeight,
        },
        style: style,
        z: z,
      });
      _dropShadow.add(jobRect);

      var travelLineStartY = pointArrival[1] + barHeight * -0;

      let jobStartCircle = new echarts.graphic.Circle({
        shape: {
          cx: pointArrival[0] - travelTime,
          cy: travelLineStartY,
          r: barHeight / 3,
        },
        style: style,
        z: z,
      });
      _dropShadow.add(jobStartCircle);

      let jobStartLine = new echarts.graphic.Line({
        shape: {
          x1: pointArrival[0] - travelTime,
          y1: travelLineStartY,
          x2: pointArrival[0],
          y2: travelLineStartY,
        },
        style: style,
        z: z,
      });
      _dropShadow.add(jobStartLine);

      /*
      console.log(
        "single job result, query (",
        date_formatter_hhmm(this.singleJobDropCheckOptions.timeArrival),
        "), result: ",
        flag,
        "minutes:",
        data["travel_time"]
      )

      var overallJobMessage = "Error" // '<font color="red">Error</font>';
      if (data["score"] == 1) {
        overallJobMessage = "OK" // '<font color="green">OK</font>';
      } else {
        overallJobMessage = "Warning" // '<font color="yellow">Warning</font>';
      }

      var messageTextArray = [
        overallJobMessage +
          "|" +
          this.singleJobDropCheckOptions.workerCode +
          ` (start: ${date_formatter_hhmm(this.singleJobDropCheckOptions.timeArrival)}) }`
      ]
      var messageText = ""
      var messageHead = "{" + flag + "|" + this.singleJobDropCheckOptions.workerCode + "-->"
      data["messages"].forEach(function(messageDict) {
        messageText = messageText + ` \n (${messageDict["score"]}: ${messageDict["messages"]})`
        messageTextArray.push(`(${messageDict["score"]}: ${messageDict["messages"]})`)
      })
      let jobDropCheckResultText = new echarts.graphic.Text({
        style: {
          x: pointArrival[0] - 100,
          y: travelLineStartY + 20,
          text:
            messageHead +
            ` (start: ${date_formatter_hhmm(
              this.singleJobDropCheckOptions.timeArrival
            )}) } ${messageText} `, //messageTextArray.join('\n'),
          //textVerticalAlign: 'bottom',
          //textAlign: 'left',
          //fill: '#FFFFFF',
          //textFill: '#333', //rgba(255, 255, 255, 0.1)

          rich: {
            OK: {
              fontSize: 12,
              color: "green"
            },
            Warning: {
              fontSize: 12,
              color: "rgba(255, 193, 7, 1)"
            },
            Error: {
              fontSize: 12,
              color: "red"
            }
          }
        },
        z: z
      })
      _dropShadow.add(jobDropCheckResultText)
      */

      myChart.getZr().add(_dropShadow);

      //Manual throttling, wait x ms.
      _single_job_drop_check_ajay_lock = false;
    },
    //myChart, global_loaded_data, global_job_dict, plannerFilters
    initDrag() {
      var myChart = this.chart;
      var _that_vm = this;
      myChart.on("mousedown", function(param) {
        if (!_that_vm.chartDraggable || !param || param.seriesIndex == null) {
          return;
        }
        _single_job_drop_check_ajay_lock = false;
        let selectedJobEnvIndex =
          _that_vm.global_job_dict[param.value[POS_JOB_INDEX_job_code]]
            .job_index_in_all;
        let selectedJob =
          _that_vm.global_loaded_data.all_jobs_in_env[selectedJobEnvIndex];
        if (selectedJob.scheduled_worker_codes.length > 1) {
          console.log(
            `Shared visits can not be moved: ${param.value[POS_JOB_INDEX_job_code]}`
          );
          return;
        }
        if (param.value[POS_JOB_INDEX_job_code].substring(0, 3) == "EVT") {
          console.log(
            `Event EVT_ can not be moved: ${param.value[POS_JOB_INDEX_job_code]}, job_type = ${selectedJob.job_type}`
          );
          return;
        }
        _that_vm.$store.commit("gantt/SET_SELECTED", {
          job: selectedJob,
        });

        let local_start = new Date(
          param.value[POS_JOB_INDEX_start_datetime]
        ).getTime();
        let local_end = new Date(
          param.value[POS_JOB_INDEX_end_datetime]
        ).getTime();

        // Drag start
        _draggingRecord = {
          dataIndex: param.dataIndex,
          categoryIndex: param.value[POS_JOB_INDEX_worker_index],
          timeArrival: local_start,
          timeDeparture: local_end,
        };
        var style = { fill: "rgba(0,0,0,0.4)" };

        _draggingEl = addOrUpdateBar(_draggingEl, _draggingRecord, style, 100);
        _draggingCursorOffset = [
          _draggingEl.position[0] - param.event.offsetX,
          _draggingEl.position[1] - param.event.offsetY,
        ];
        _draggingTimeLength =
          _draggingRecord.timeDeparture - _draggingRecord.timeArrival;
      });

      myChart.getZr().on("mousemove", function(event) {
        //console.log(event)
        if (!_draggingEl) {
          return;
        }

        var cursorX = event.offsetX;
        var cursorY = event.offsetY;

        // Move _draggingEl.
        _draggingEl.attr("position", [
          _draggingCursorOffset[0] + cursorX,
          _draggingCursorOffset[1] + cursorY,
        ]);

        _that_vm.prepareDrop();

        //autoDataZoomWhenDraggingOutside(cursorX, cursorY);
      });

      myChart.getZr().on("mouseup", function() {
        // Drop
        // console.log('mouseup updateRawData, duan 2020-02-19 18:42:23')

        if (_draggingEl && _dropRecord) {
          _that_vm.updateRawData(); // &&
        }
        // console.log(_dropRecord, "mouseup triggered, calling dragRelease")
        dragRelease();
      });
      myChart.getZr().on("globalout", dragRelease);

      function dragRelease() {
        if (_draggingEl) {
          myChart.getZr().remove(_draggingEl);
          _draggingEl = null;
        }
        if (_dropShadow) {
          myChart.getZr().remove(_dropShadow);
          _dropShadow = null;
        }

        _dropRecord = _draggingRecord = null;
        // console.log("dragRelease is Done", _dropRecord, _draggingRecord)
      }

      function addOrUpdateBar(el, itemData, style, z) {
        var pointArrival = myChart.convertToPixel("grid", [
          itemData.timeArrival,
          itemData.categoryIndex,
        ]);
        var pointDeparture = myChart.convertToPixel("grid", [
          itemData.timeDeparture,
          itemData.categoryIndex,
        ]);

        var barLength = pointDeparture[0] - pointArrival[0];
        var barHeight =
          Math.abs(
            myChart.convertToPixel("grid", [0, 0])[1] -
              myChart.convertToPixel("grid", [0, 1])[1]
          ) * HEIGHT_RATIO;

        if (!el) {
          el = new echarts.graphic.Rect({
            shape: { x: 0, y: 0, width: 0, height: 0 },
            style: style,
            z: z,
          });
          myChart.getZr().add(el);
        }
        el.attr({
          shape: { x: 0, y: 0, width: barLength, height: barHeight },
          position: [
            pointArrival[0],
            pointArrival[1] - barHeight + barHeight / 2,
          ],
        });
        return el;
      }
    },

    addOrUpdateDroppingJob() {
      if (_single_job_drop_check_ajay_lock) {
        // Last api call is not finished yet.
        // console.log("Last api call is not finished yet, not to check: ", _dropRecord)
        return;
      }
      // else {
      // console.log("Last api call is already finished, to check : _dropRecord =", _dropRecord)
      // }
      _single_job_drop_check_ajay_lock = true;

      console.log("to check _dropRecord.jobCode: ", _dropRecord.jobCode);

      // alert("todo /kpdata/single_job_drop_check.json ")
      /* Moved to store.js
      let plannerFilters = this.plannerFilters
      var jobActionOptions = {
        team_id: plannerFilters.team.id, //3,
        start_day: plannerFilters.windowDates[0].replace("-", "").replace("-", ""), //"TODO",
        end_day: plannerFilters.windowDates[1].replace("-", "").replace("-", ""),
        scheduled_secondary_worker_ids: []
      }
      */

      var jobActionOptions = {};
      console.log("to check _dropRecord.jobCode: ", _dropRecord.jobCode);

      jobActionOptions.job_code = _dropRecord.jobCode;
      jobActionOptions.scheduled_start_datetime = formatISO(
        new Date(_dropRecord.timeArrival)
      );
      jobActionOptions.scheduled_duration_minutes =
        (_dropRecord.timeDeparture - _dropRecord.timeArrival) / 1000 / 60;
      jobActionOptions.scheduled_primary_worker_id = _dropRecord.workerCode;
      jobActionOptions.scheduled_secondary_worker_ids = [];
      /*
      jobActionOptions.scheduled_start_minutes = parseInt(
        (_dropRecord.timeArrival - new Date(this.plannerFilters.windowDates[0]).getTime()) /
          1000 /
          60
      )*/

      jobActionOptions.categoryIndex = _dropRecord.categoryIndex;
      jobActionOptions.timeArrival = _dropRecord.timeArrival;
      jobActionOptions.timeDeparture = _dropRecord.timeDeparture;

      //console.log(jobActionOptions)

      this.doSingleJobDropCheck(jobActionOptions);
    },

    prepareDrop() {
      let global_loaded_data = this.global_loaded_data;
      // Check droppable place.
      var xPixel = _draggingEl.shape.x + _draggingEl.position[0];
      var yPixel = _draggingEl.shape.y + _draggingEl.position[1];
      var cursorData = this.chart.convertFromPixel("grid", [xPixel, yPixel]);
      let workerIndex = Math.floor(cursorData[1]);

      if (
        workerIndex >= global_loaded_data.workers_data.length ||
        workerIndex < 0
      ) {
        console.log("Out of Workers Boundary!", workerIndex);
        return;
      }

      let currWorkerCode =
        global_loaded_data.workers_data[workerIndex][
          POS_WORKER_INDEX_worker_code
        ];

      if (cursorData) {
        // Make drop shadow and _dropRecord
        _dropRecord = {
          categoryIndex: workerIndex,
          workerCode: currWorkerCode,
          timeArrival: cursorData[0],
          timeDeparture: cursorData[0] + _draggingTimeLength,
          travelMinutes: 0,
          jobCode:
            global_loaded_data.planned_jobs_data[_draggingRecord.dataIndex][
              POS_JOB_INDEX_job_code
            ],
        };

        this.addOrUpdateDroppingJob();
      }
      // console.log('prepareDrop:', _draggingEl, _dropRecord, cursorData)
    },

    // Business logic to
    updateRawData() {
      let global_loaded_data = this.global_loaded_data;
      //var flightData = ;
      //var movingItem = global_loaded_data.planned_jobs_data.pop(_draggingRecord.dataIndex);
      var movingItem =
        global_loaded_data.planned_jobs_data[_draggingRecord.dataIndex];

      // I simply drop it .
      movingItem[POS_JOB_INDEX_worker_index] =
        global_loaded_data.workers_data[_dropRecord.categoryIndex][0];

      // This might convert to a string with timezone, which is different from server-loaded data.
      movingItem[POS_JOB_INDEX_start_datetime] = new Date(
        _dropRecord.timeArrival
      ).toISOString();
      movingItem[POS_JOB_INDEX_end_datetime] = new Date(
        _dropRecord.timeDeparture
      ).toISOString();
      movingItem[POS_JOB_INDEX_changed_flag] = 1;

      // let global_job_dict = this.global_job_dict
      // let jobType = movingItem[POS_JOB_INDEX_job_type]
      // let conflict_level = movingItem[POS_JOB_INDEX_conflict_level]
      // let node_itemStyle = getNodeItemStyle(jobType, conflict_level) //Type, conflict_level
      // global_job_dict[movingItem[POS_JOB_INDEX_job_code]]["node_item_style"] = node_itemStyle

      //newIndex = global_loaded_data.planned_jobs_data.push(movingItem) - 1;
      //global_job_dict[movingItem[POS_JOB_INDEX_job_code]]['job_index'] = newIndex

      //global_loaded_data.planned_jobs_data.splice(_draggingRecord.dataIndex, 0, movingItem);
      //console.log(global_loaded_data.planned_jobs_data)
      this.chart.setOption({
        series: {
          id: "jobsSeries",
          data: global_loaded_data.planned_jobs_data,
        },
      });
      return true;
    },
  },
};
</script>
