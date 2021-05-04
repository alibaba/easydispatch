<template>
  <v-combobox
    v-model="worker"
    prepend-icon="person"
    :items="items"
    item-text="code"
    :search-input.sync="search"
    :menu-props="{ maxHeight: '400' }"
    :label="label"
    :loading="loading"
    @update:search-input="fetchData({ q: $event })"
  >
    <template v-slot:no-data>
      <v-list-item>
        <v-list-item-content>
          <v-list-item-title>
            No Workers matching "
            <strong>{{ search }}</strong
            >".
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script>
import WorkerApi from "@/worker/api";
import { cloneDeep } from "lodash";
export default {
  name: "WorkerSelect",
  props: {
    value: {
      type: Object,
      default: function() {
        return {};
      }
    },
    label: {
      type: String,
      default: function() {
        return "Worker";
      }
    }
  },

  data() {
    return {
      loading: false,
      items: [],
      search: null
    };
  },

  computed: {
    worker: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      }
    }
  },

  created() {
    this.fetchData({});
  },

  methods: {
    fetchData(filterOptions) {
      this.error = null;
      this.loading = true;
      WorkerApi.getAll(filterOptions).then(response => {
        this.items = response.data.items;
        this.loading = false;
      });
    }
  }
};
</script>
