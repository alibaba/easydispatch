<template>
  <v-layout wrap>
    <edit-sheet />
    <new-sheet />
    <!--<delete-dialog />-->
    <div class="headline">Jobs</div>
    <v-spacer />
    <v-btn color="primary" dark class="ml-2" @click="showNewSheet()">New</v-btn>
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
              <template v-slot:item.cost="{ item }">
                {{
                item.cost | toUSD
                }}
              </template>
              <template v-slot:item.commander="{ item }">
                <div v-if="item.commander">
                  <v-chip class="ma-2" pill small :href="item.commander.weblink">
                    <div v-if="item.commander.name">{{ item.commander.name }}</div>
                    <div v-else>{{ item.commander.code }}</div>
                  </v-chip>
                </div>
              </template>
              <template v-slot:item.reporter="{ item }">
                <div v-if="item.reporter">
                  <v-chip class="ma-2" pill small :href="item.reporter.weblink">
                    <div v-if="item.reporter.name">{{ item.reporter.name }}</div>
                    <div v-else>{{ item.reporter.code }}</div>
                  </v-chip>
                </div>
              </template>
              <template v-slot:item.reported_at="{ item }">
                {{
                item.reported_at | formatDate
                }}
              </template>
              <template v-slot:item.data-table-actions="{ item }">
                <v-menu bottom left>
                  <template v-slot:activator="{ on }">
                    <v-btn icon v-on="on">
                      <v-icon>mdi-dots-vertical</v-icon>
                    </v-btn>
                  </template>
                  <v-list>
                    <v-list-item @click="showEditSheet(item)">
                      <v-list-item-title>Edit</v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-menu>
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

export default {
  name: "JobTable",

  components: {
    EditSheet,
    NewSheet,
  },

  props: ["name"],

  data() {
    return {
      headers: [
        // { text: "ID", value: "id", align: "left" },
        { text: "Job Name", value: "name" },
        { text: "Job Code", value: "code" },
        ,
        { text: "Status", value: "planning_status" },
        { text: "Description", value: "description" },
        { text: "Requested Worker", value: "requested_primary_worker.code" },
        { text: "Requested Start", value: "requested_start_datetime" },
        { text: "Requested Minutes", value: "requested_duration_minutes" },
        { text: "Scheduled Primary", value: "scheduled_primary_worker.code" },
        { text: "scheduled Start", value: "scheduled_start_datetime" },
        { text: "Scheduled Minutes", value: "scheduled_duration_minutes" },
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
  },

  mounted() {
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

  methods: {
    ...mapActions("job", [
      "getAll",
      "showNewSheet",
      "showEditSheet",
      "removeShow",
    ]),
  },
};
</script>
