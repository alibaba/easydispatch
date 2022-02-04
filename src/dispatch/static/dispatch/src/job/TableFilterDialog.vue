<template>
  <v-dialog v-model="display" max-width="600px">
    <template v-slot:activator="{ on }">
      <v-badge :value="numFilters" bordered overlap :content="numFilters">
        <v-btn color="secondary" dark v-on="on">Filter Columns</v-btn>
      </v-badge>
    </template>
    <v-card>
      <v-card-title>
        <span class="headline">Column Filters</span>
      </v-card-title>
      <v-list dense>
        <v-list-item>
          <v-list-item-content>
            <tag-filter-combobox v-model="tag" label="Tags" />
          </v-list-item-content>
        </v-list-item>
        <v-list-item>
          <v-list-item-content>
            <job-status-multi-select v-model="status" />
          </v-list-item-content>
        </v-list-item>
      </v-list>
    </v-card>
  </v-dialog>
</template>

<script>
import { sum } from "lodash";
import { mapFields } from "vuex-map-fields";
import JobStatusMultiSelect from "@/job/JobStatusMultiSelect.vue";
// import WorkerCombobox from "@/worker/WorkerCombobox.vue"
import TagFilterCombobox from "@/tag/TagFilterCombobox.vue";

export default {
  name: "JobTableFilterDialog",

  components: {
    // WorkerCombobox,
    TagFilterCombobox,
    JobStatusMultiSelect
  },

  data() {
    return {
      display: false
    };
  },

  computed: {
    ...mapFields("job", [
      "table.options.filters.commander",
      "table.options.filters.reporter",
      "table.options.filters.job_type",
      "table.options.filters.status",
      "table.options.filters.tag"
    ]),
    numFilters: function() {
      return sum([
        this.reporter.length,
        this.commander.length,
        this.job_type.length,
        this.tag.length,
        this.status.length
      ]);
    }
  }
};
</script>
