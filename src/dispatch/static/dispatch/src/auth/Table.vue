<template>
  <v-layout wrap>
    <new-edit-sheet />
    <delete-dialog />
    <div class="headline">Users</div>
    <v-spacer />
    <v-flex xs12>
      <v-layout column>
        <v-flex>
          <v-card>
            <v-card-title>
              <v-text-field
                v-model="q"
                append-icon="search"
                label="Search"
                single-line
                hide-details
                clearable
                :loading="loading"
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
            >
              <template v-slot:item.data-table-actions="{ item }">
                <span class="table_action_icon">
                  <v-icon small class="mr-2" @click="editShow(item)">mdi-pencil</v-icon>
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
import NewEditSheet from "@/auth/editSheet.vue";
import DeleteDialog from "@/auth/DeleteDialog.vue";
export default {
  name: "UserTable",

  components: {
    NewEditSheet,
    DeleteDialog,
  },
  data() {
    return {
      headers: [
        { text: "Email", value: "email", sortable: true },
        { text: "Role", value: "role", sortable: true },
        { text: "Default Team", value: "team.code", sortable: true },
        { text: "Active", value: "is_active", sortable: true },
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
    ...mapFields("auth", [
      "table.options.q",
      "table.options.page",
      "table.options.itemsPerPage",
      "table.options.sortBy",
      "table.options.descending",
      "table.options.loading",
      "table.rows.items",
      "table.rows.total",
    ]),
  },

  mounted() {
    this.getAll({});

    this.$watch(
      (vm) => [vm.q, vm.page, vm.itemsPerPage, vm.sortBy, vm.descending],
      () => {
        this.getAll();
      }
    );
  },
  destroyed() {
    this.closeEdit();
  },
  methods: {
    ...mapActions("auth", ["getAll", "editShow", "removeShow", "closeEdit"]),
    doRegisterCode() {},
  },
};
</script>
<style>
.table_action_icon {
  white-space: nowrap;
}
</style>