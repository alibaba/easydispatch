<template>
  <v-layout wrap>
    <new-edit-sheet />
    <delete-dialog />
    <div class="headline">Teams</div>
    <v-spacer />
    <v-btn
      color="primary"
      dark
      class="mb-2"
      @click="createEditShow()"
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
                label="Search by code, name"
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
              <template v-slot:item.reset-window="{ item }">
                <v-icon small class="mr-2" @click="reset_planning_window(item.code)">mdi-reload</v-icon>
              </template>
              <template v-slot:item.data-table-actions="{ item }">
                <span class="table_action_icon">
                  <v-icon small class="mr-2" @click="createEditShow(item)">mdi-pencil</v-icon>
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
import DeleteDialog from "@/team/DeleteDialog.vue";
import NewEditSheet from "@/team/NewEditSheet.vue";
import { mapState } from "vuex";
export default {
  name: "TeamTable",

  components: {
    DeleteDialog,
    NewEditSheet,
  },
  data() {
    return {
      headers: [
        { text: "Code", value: "code", sortable: true },
        { text: "Name", value: "name", sortable: true },
        {
          text: "Planner Service",
          value: "planner_service.code",
          sortable: false,
        },
        {
          text: "Reset Window",
          value: "reset-window",
          sortable: false,
          align: "center",
        },
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
    ...mapFields("team", [
      "table.options.q",
      "table.options.page",
      "table.options.itemsPerPage",
      "table.options.sortBy",
      "table.options.descending",
      "table.loading",
      "table.rows.items",
      "table.rows.total",
    ]),
    ...mapState("auth", ["userInfo"]),
  },

  mounted() {
    this.getOrg();
    this.getAll({});

    this.$watch(
      (vm) => [vm.page],
      () => {
        this.getAll();
      }
    );

    this.$watch(
      (vm) => [vm.q, vm.itemsPerPage, vm.sortBy, vm.descending],
      () => {
        this.page = 1;
        this.getAll();
      }
    );
  },
  destroyed() {
    this.closeCreateEdit();
  },
  methods: {
    ...mapActions("team", [
      "getAll",
      "createEditShow",
      "removeShow",
      "reset_planning_window",
      "closeCreateEdit",
    ]),
    ...mapActions("org", ["getOrg"]),
  },
};
</script>
<style>
.table_action_icon {
  white-space: nowrap;
}
</style>