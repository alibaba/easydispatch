<template>
  <v-combobox
    v-model="worker"
    prepend-icon="people"
    :items="items"
    item-text="code"
    :search-input.sync="search"
    :menu-props="{ maxHeight: '400' ,closeOnClick: true, closeOnContentClick: true,}"
    hide-selected
    :label="label"
    multiple
    close
    chips
    clearable
    :loading="loading"
    @update:search-input="fetchData({ q: $event })"
    dense
  >
    <template v-slot:no-data>
      <v-list-item>
        <v-list-item-content>
          <v-list-item-title>
            No Indivduals matching "
            <strong>{{ search }}</strong>".
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script>
import WorkerApi from "@/worker/api";
import { cloneDeep, debounce } from "lodash";
export default {
  name: "WorkerCombo",
  props: {
    value: {
      type: Array,
      default: function () {
        return [];
      },
    },
    label: {
      type: String,
      default: function () {
        return "Worker";
      },
    },
  },

  data() {
    return {
      loading: false,
      items: [],
      search: null,
    };
  },

  computed: {
    worker: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this._workers = value.map((v) => {
          if (typeof v === "string") {
            v = {
              name: v,
            };
            this.items.push(v);
          }
          return v;
        });
        this.$emit(
          "input",
          this._workers.filter((row) => row.code != undefined)
        );
      },
    },
  },

  created() {
    this.fetchData({});
  },

  methods: {
    fetchData: debounce(function (filterOptions) {
      this.error = null;
      this.loading = true;
      WorkerApi.getAll(filterOptions).then((response) => {
        this.items = response.data.items;
        this.loading = false;
      });
    }, 200),
  },
};
</script>
