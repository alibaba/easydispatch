<template>
  <v-layout row wrap>
    <v-flex xs12>
      <header class="top-bar">
        <el-form :inline="true" size="small">
          <el-form-item label="time range">
            <el-date-picker
              v-model="times"
              size="small"
              type="datetimerange"
              range-separator="to"
              start-placeholder="begin time"
              end-placeholder="end time"
              style="width:350px"
            ></el-date-picker>
          </el-form-item>
          <el-form-item label="rows">
            <el-input v-model.number="rowNum" size="small" style="width:60px" placeholder></el-input>
          </el-form-item>
          <el-form-item label="columns">
            <el-input v-model.number="colNum" size="small" style="width:60px" placeholder></el-input>
          </el-form-item>
          <el-form-item label="cellHeight">
            <el-slider v-model="cellHeight" :min="20" :max="100" style="width:40px" size="small"></el-slider>
          </el-form-item>
          <el-form-item label="cellWidth">
            <el-slider v-model="cellWidth" :min="20" :max="100" style="width:40px" size="small"></el-slider>
          </el-form-item>
          <el-form-item label="scale">
            <el-select v-model="scale" placeholder style="width:120px" size="small">
              <el-option
                v-for="item in scaleList"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              ></el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="team">
            <el-select v-model="team_id" placeholder style="width:120px" size="small">
              <el-option
                v-for="item in team_list"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              ></el-option>
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-checkbox v-model="hideHeader">hideHeader</el-checkbox>
          </el-form-item>
        </el-form>
      </header>
    </v-flex>
    <v-flex xs12>
      <v-layout column>
        <v-flex>
          <v-card>
            <v-gantt-chart
              :startTime="times[0]"
              :endTime="times[1]"
              :cellWidth="cellWidth"
              :cellHeight="cellHeight"
              :timeLines="timeLines"
              :titleHeight="titleHeight"
              :scale="scale"
              :titleWidth="titleWidth"
              showCurrentTime
              :hideHeader="hideHeader"
              :dataKey="dataKey"
              :arrayKeys="arrayKeys"
              :scrollToPostion="positionA"
              @scrollLeft="scrollLeftA"
              :datas="filterDatas"
            >
              <template v-slot:block="{ data, item }">
                <Test
                  :data="data"
                  :updateTimeLines="updateTimeLines"
                  :cellHeight="cellHeight"
                  :currentTime="currentTime"
                  :item="item"
                ></Test>
              </template>
              <template v-slot:left="{ data }">
                <TestLeft :data="data"></TestLeft>
              </template>
              <template v-slot:title>planed jobs history</template>
            </v-gantt-chart>
          </v-card>
        </v-flex>
      </v-layout>
    </v-flex>
  </v-layout>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import Test from "./components/test.vue";
import TestLeft from "./components/test-left.vue";
import TestTimeline from "./components/test-timeline.vue";
import TestMarkline from "./components/test-markline.vue";
import { mockDatas } from "./mock/index.js";
import VGanttChart from "v-gantt-chart";
import dayjs from "dayjs";
import Vue from "vue";
import ElementUI from "element-ui"; //element-ui的全部组件
import "element-ui/lib/theme-chalk/index.css"; //element-ui的css
Vue.use(ElementUI); //使用elementUI
const scaleList =
  `1,2,3,4,5,6,10,12,15,20,30,60,120,180,240,360,720,1440,2880,4320`
    .split(",")
    .map((n) => {
      let value = parseInt(n);
      let label;
      if (value < 60) {
        label = value + "minute";
      } else if (value >= 60 && value < 1440) {
        label = value / 60 + "hour";
      } else {
        label = value / 1440 + "day";
      }
      return {
        value,
        label,
      };
    });
export default {
  name: "App",
  components: { Test, TestLeft, TestTimeline, TestMarkline, VGanttChart },
  data() {
    return {
      timeLines: [
        {
          time: dayjs().add(2, "hour").toString(),
          text: "~~",
        },
        {
          time: dayjs().add(5, "hour").toString(),
          text: "try",
          color: "#747e80",
        },
      ],
      currentTime: dayjs(),
      cellWidth: 100,
      cellHeight: 30,
      titleHeight: 40,
      titleWidth: 250,
      scale: 60,
      dataKey: "id",
      scaleList: scaleList,
      scrollToTime: dayjs().add(1, "day").toString(),
      scrollToPostion: { x: 10000, y: 10000 },
      hideHeader: false,
      hideSecondGantt: false,
      arrayKeys: ["gtArray", "error"],
      scrollToY: 0,
      positionB: {},
      positionA: {},
    };
  },
  watch: {
    rowNum: "getPlanJobs",
    colNum: "getPlanJobs",
    times: "getPlanJobs",
    team_id: "getPlanJobs",
    scrollToY(val) {
      this.positionA = { x: val };
    },
  },
  computed: {
    ...mapFields("plan_jobs", [
      "data.datas",
      "data.loading",
      "data.rowNum",
      "data.colNum",
      "data.times",
      "data.team_id",
      "data.team_list",
    ]),
    filterDatas: {
      get() {
        return Object.values(this.datas.slice(0, this.rowNum)).reduce(
          (pre, cur, index) => {
            if (this.colNum != undefined && this.colNum > 0) {
              return [
                ...pre,
                { ...cur, gtArray: cur.gtArray.slice(0, this.colNum) },
              ];
            } else {
              return [...pre, cur];
            }
          },
          []
        );
      },
    },
  },
  mounted() {
    let that = this;
    this.$store.dispatch("plan_jobs/getTeams", {
      success() {
        that.getPlanJobs();
      },
    });
  },
  methods: {
    ...mapActions("plan_jobs", ["getPlanJobs", "getTeams"]),
    updateTimeLines(timeA, timeB) {
      this.timeLines = [
        {
          time: timeA,
          text: "自定义",
        },
        {
          time: timeB,
          text: "测试",
          color: "#747e80",
        },
      ];
    },
    scrollLeftA(val) {
      this.positionB = { x: val };
    },
  },
};
</script>

<style scoped>
body {
  font: 12px;
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
}
#app {
  display: flex;
  flex-direction: column;
  padding: 0 10px;
  height: calc(100vh - 2px);
}
label {
  margin-left: 10px;
}
input {
  width: 40px;
  height: 20px;
  vertical-align: middle;
}
input[type="range"] {
  width: 100px;
}
.container {
  height: calc(100% - 58px);
  display: flex;
  flex-direction: column;
  flex: 1;
}
.main-footer {
  /* height: 30px; */
}
.el-slider {
  width: 100px;
}
</style>