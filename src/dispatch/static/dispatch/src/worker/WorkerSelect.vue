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
    @update:search-input="getAll({ q: $event })"
  >
    <template v-slot:no-data>
      <v-list-item>
        <v-list-item-content>
          <v-list-item-title>
            No Workers matching "
            <strong>{{ search }}</strong>".
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script>
import { cloneDeep } from "lodash";
import { mapActions } from "vuex";
import { mapFields } from "vuex-map-fields";
export default {
  name: "WorkerSelect",
  props: {
    value: {
      type: Object,
      default: function () {
        return {};
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
      search: null,
    };
  },

  computed: {
    ...mapFields("worker", ["table.loading", "table.rows.items"]),
    worker: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },

  created() {
    this.getAll();
  },

  methods: {
    ...mapActions("worker", ["selectWorker", "getAll"]),
  },
};
</script>
