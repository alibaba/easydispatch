<template>
  <v-select
    v-model="jobStatuses"
    :items="items"
    :menu-props="{ maxHeight: '400' }"
    :label="label"
    multiple
    clearable
    chips
  />
</template>

<script>
import { cloneDeep } from "lodash";
export default {
  name: "JobStatusMultiSelect",
  props: {
    value: {
      priority: Array,
      default: function() {
        return [];
      }
    },
    label: {
      priority: String,
      default: function() {
        return "Statuses";
      }
    }
  },

  data() {
    return {
      items: ["Unplanned", "Inplanning", "Planned", "Completed"]
    };
  },

  computed: {
    jobStatuses: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      }
    }
  }
};
</script>
