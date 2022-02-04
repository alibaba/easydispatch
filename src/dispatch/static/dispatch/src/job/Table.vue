<template>
  <v-layout wrap>
    <edit-sheet />
    <new-sheet />
    <delete-dialog />
    <div class="headline">Jobs</div>
    <v-spacer />
    <v-btn
      color="primary"
      dark
      class="ml-2"
      @click="showNewSheet()"
      :disabled="!userInfo || userInfo.role=='User' "
    >New</v-btn>
    <v-flex xs12>
      <v-layout column>
        <v-flex>
          <v-card>
            <v-card-title>
              <v-text-field
                v-model="q"
                append-icon="search"
                label="Search by code, name, description"
                single-line
                hide-details
                clearable
              />
            </v-card-title>
            <v-data-table
              :headers="headers"
              :items="items"
              :server-items-length="total"
              :page.sync="page"
              :items-per-page.sync="itemsPerPage"
              :sort-by.sync="sortBy"
              :sort-desc.sync="descending"
              :loading="loading"
              loading-text="Loading... Please wait"
            >
              <template v-slot:item.reported_at="{ item }">
                {{
                item.reported_at | formatDate
                }}
              </template>
              <template v-slot:item.description="{ item }">
                <v-tooltip bottom>
                  <template v-slot:activator="{ on, attrs }">
                    <span
                      class="overflow_ellipsis_col"
                      v-bind="attrs"
                      v-on="on"
                    >{{item.description}}</span>
                  </template>
                  <span>{{item.description}}</span>
                </v-tooltip>
              </template>

              <template v-slot:item.data-table-actions="{ item }">
                <span class="table_action_icon">
                  <v-icon small class="mr-2" @click="showEditSheet(item)">mdi-pencil</v-icon>
                  <v-icon small @click="removeShow(item)">mdi-delete</v-icon>
                </span>
              </template>
            </v-data-table>
          </v-card>
        </v-flex>
      </v-layout>
    </v-flex>
  </v-layout>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import EditSheet from "@/job/EditSheet.vue";
import NewSheet from "@/job/NewSheet.vue";
import DeleteDialog from "@/job/DeleteDialog.vue";
import { mapState } from "vuex";

export default {
  name: "JobTable",

  components: {
    EditSheet,
    NewSheet,
    DeleteDialog,
  },

  props: ["name"],
  data() {
    return {
      scheduled_worker_filter: null,
      headers: [
        // { text: "ID", value: "id", align: "left" },
        { text: "Job Code", value: "code" },
        { text: "Team", value: "team.code", sortable: true },
        { text: "Status", value: "planning_status" },
        {
          text: "Scheduled Primary",
          value: "scheduled_primary_worker.code",
          sortable: false,
          filter: (value) => {
            if (!this.scheduled_worker_filter) return true;
            return value
              .toLowerCase()
              .startsWith(this.scheduled_worker_filter.toLowerCase());
            //return value == this.status_filter
          },
        },
        { text: "scheduled Start", value: "scheduled_start_datetime" },
        { text: "Scheduled Minutes", value: "scheduled_duration_minutes" },
        // { text: "Requested Worker", value: "requested_primary_worker.code" },
        // { text: "Requested Start", value: "requested_start_datetime" },
        // { text: "Requested Minutes", value: "requested_duration_minutes" },
        // { text: "Description", value: "description" },
        {
          text: "",
          value: "data-table-actions",
          sortable: false,
          align: "end",
        },
      ],
    };
  },

  computed: {
    ...mapFields("job", [
      "table.options.q",
      "table.options.page",
      "table.options.itemsPerPage",
      "table.options.sortBy",
      "table.options.filters.planning_status",
      "table.options.filters.tag",
      "table.options.descending",
      "table.loading",
      "table.rows.items",
      "table.rows.total",
    ]),
    ...mapState("auth", ["userInfo"]),
  },

  mounted() {
    this.getOrg();
    // process our props
    if (this.name) {
      this.q = this.name;
    }
    this.getAll();

    this.$watch(
      (vm) => [vm.page],
      () => {
        this.getAll();
      }
    );

    this.$watch(
      (vm) => [
        vm.q,
        vm.sortBy,
        vm.itemsPerPage,
        vm.descending,
        vm.planning_status,
        vm.tag,
      ],
      () => {
        this.page = 1;
        this.getAll();
      }
    );
  },
  destroyed() {
    this.closeEditSheet();
    this.closeNewSheet();
  },
  methods: {
    ...mapActions("job", [
      "getAll",
      "showNewSheet",
      "showEditSheet",
      "removeShow",
      "closeNewSheet",
      "closeEditSheet",
    ]),
    ...mapActions("org", ["getOrg"]),
  },
};
</script>
<style>
.overflow_ellipsis_col {
  display: block;
  max-width: 200px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.table_action_icon {
  white-space: nowrap;
}
</style>