<template>
  <v-layout wrap>
    <new-edit-sheet />
    <delete-dialog />
    <div class="headline">Inventory Quantities per Item and Depot</div>
    <v-spacer />
    <v-btn color="primary" dark class="mb-2" @click="createEditShow()">New</v-btn>
    <v-flex xs12>
      <v-layout column>
        <v-flex>
          <v-card>
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
import DeleteDialog from "@/item_inventory/DeleteDialog.vue";
import NewEditSheet from "@/item_inventory/NewEditSheet.vue";
import { mapState } from "vuex";
export default {
  name: "ItemInventoryTable",

  components: {
    DeleteDialog,
    NewEditSheet,
  },
  data() {
    return {
      headers: [
        {
          text: "Depot Code",
          value: "depot.code",
          sortable: true,
          align: "center",
        },
        {
          text: "Item Code",
          value: "item.code",
          sortable: true,
          align: "center",
        },
        {
          text: "Max Quantity",
          value: "max_qty",
          sortable: false,
          align: "center",
        },
        {
          text: "Current",
          value: "curr_qty",
          sortable: false,
          align: "center",
        },
        {
          text: "Allocated",
          value: "allocated_qty",
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
    ...mapFields("item_inventory", [
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
    ...mapActions("item_inventory", [
      "getAll",
      "createEditShow",
      "removeShow",
      "closeCreateEdit",
    ]),
  },
};
</script>
<style>
.table_action_icon {
  white-space: nowrap;
}
</style>