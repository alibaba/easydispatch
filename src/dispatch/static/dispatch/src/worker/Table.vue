<template>
  <v-layout wrap>
    <new-edit-sheet />
    <delete-dialog />
    <div class="headline">Workers</div>
    <v-spacer />
    <v-btn color="primary" dark class="mb-2" @click="createEditShow()">New</v-btn>
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
              <template v-slot:item.is_active="{ item }">
                <v-simple-checkbox v-model="item.is_active" disabled></v-simple-checkbox>
              </template>
              <template v-slot:item.is_external="{ item }">
                <v-simple-checkbox v-model="item.is_external" disabled></v-simple-checkbox>
              </template>
              <template v-slot:item.data-table-actions="{ item }">
                <span class="table_action_icon">
                  <v-icon small class="mr-2" @click="createEditShow(item)">mdi-pencil</v-icon>
                  <v-icon small @click="removeShow(item)">mdi-delete</v-icon>
                </span>
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
import DeleteDialog from "@/worker/DeleteDialog.vue";
import NewEditSheet from "@/worker/NewEditSheet.vue";
export default {
  name: "WorkerTable",

  components: {
    DeleteDialog,
    NewEditSheet,
  },
  data() {
    return {
      headers: [
        // { text: "ID", value: "id", sortable: true },
        { text: "Code", value: "code", sortable: true },
        { text: "Team", value: "team.code", sortable: true },
        { text: "Name", value: "name", sortable: true },
        { text: "Description", value: "description", sortable: true },
        { text: "Active", value: "is_active", sortable: true },
        // { text: "Linked Username", value: "username", sortable: true },
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
    ...mapFields("worker", [
      "table.options.q",
      "table.options.page",
      "table.options.itemsPerPage",
      "table.options.sortBy",
      "table.options.descending",
      "table.loading",
      "table.rows.items",
      "table.rows.total",
    ]),
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
    ...mapActions("worker", [
      "getAll",
      "createEditShow",
      "removeShow",
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