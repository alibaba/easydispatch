<template>
  <el-popover placement="bottom" trigger="hover">
    <div
      slot="reference"
      class="plan"
      :style="{
        'background-color': statusColor,
        'margin-top': 0.1 * cellHeight + 'px'
      }"
      @click="onClick"
    >
      <div class="runTime">
        <span>{{ startToString }}</span>
        <!-- <span>E:{{ endToString }}</span> -->
      </div>
      <div class="middle">{{ item.name }}</div>
      <!-- <div class="passenger">{{item.passenger}}人</div> -->
    </div>

    <div class="detail">
      <span class="header">{{ item.name }}</span>
      <ul>
        <li>
          <span>start：</span>
          <span>{{ startToString }}</span>
        </li>
        <li>
          <span>end：</span>
          <span>{{ endToString }}</span>
        </li>
      </ul>
    </div>
  </el-popover>
</template>

<script>
import dayjs from "dayjs";
const NOW_PLAN = "#D5F8EA";
const FUTHER_PLAN = "#BFF2FE";
const PAST_PLAN = "#F2F2F2";
export default {
  name: "Test",
  props: {
    data: Object,
    item: Object,
    currentTime: dayjs,
    updateTimeLines: Function,
    cellHeight: Number,
    startTimeOfRenderArea: Number,
  },
  data() {
    return {
      dayjs: dayjs,
    };
  },
  computed: {
    statusColor() {
      let { item, currentTime } = this;
      let start = dayjs(item.start);
      let end = dayjs(item.end);
      if (start.isBefore(currentTime) && end.isAfter(currentTime)) {
        return NOW_PLAN; // NOW
      } else if (end.isBefore(currentTime)) {
        return PAST_PLAN; // PAST
      } else {
        return FUTHER_PLAN; // Future
      }
    },
    startToString() {
      return dayjs(this.item.start).format("HH:mm");
    },
    endToString() {
      return dayjs(this.item.end).format("HH:mm");
    },
  },
  methods: {
    onClick() {
      this.updateTimeLines(this.item.start, this.item.end);
    },
  },
};
</script>

<style lang="scss" scoped>
.middle {
  flex: 1;
  text-align: center;
  padding-left: 5px;
  color: rgba(255, 255, 255, 0.4);
}
.runTime {
  display: flex;
  flex-direction: column;
}
.plan {
  display: flex;
  align-items: center;
  box-sizing: border-box;
  height: 80%;
  border: 1px solid #f0f0f0;
  border-radius: 5px;
  color: #333333;
  padding-left: 5px;
  font-size: 0.8rem;
  // opacity: 0.8;
}
.detail {
  .header {
    text-align: center;
    font-size: 1rem;
  }
}
.detail ul {
  list-style: none;
  padding: 0px;
  li {
    span {
      display: inline-block;
      width: 80px;
      color: #777;
      font-size: 0.8rem;
    }
    span:first-child {
      text-align: right;
    }
    span:last-child {
    }
  }
}
</style>