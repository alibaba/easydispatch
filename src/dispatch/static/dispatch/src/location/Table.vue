<template>
  <v-layout wrap>
    <new-edit-sheet />
    <edit-sheet /> 
    <div class="headline">Locations</div>
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
                label="Search by code, address text"
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
              <template v-slot:item.location_code="{ item }">
                <v-tooltip bottom>
                  <template v-slot:activator="{ on, attrs }">
                    <span class="location_code" v-bind="attrs" v-on="on">{{item.location_code}}</span>
                  </template>
                  <span>{{item.location_code}}</span>
                </v-tooltip>
              </template>
              <template v-slot:item.actions="{ item }">
                <v-icon small v-show="getPermission()('location.button.customer_create_job')"
                  class="mr-2" @click="clickNewJobOnLocation( item)">star</v-icon>
                <v-icon small class="mr-2" @click="createEditShow(item)">mdi-pencil</v-icon>
              </template>
              <template v-slot:item.geo_address_text="{ item }">
                <div class="text-truncate" style="max-width: 500px;">{{ item.geo_address_text }}</div>
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
import { mapGetters } from "vuex";
import { mapState } from "vuex";

import  EditSheet   from "@/job/JobEdit4Customer.vue"; 

import NewEditSheet from "@/location/NewEditSheet.vue";
export default {
  name: "LocationTable",

  components: {
    NewEditSheet,
    EditSheet,
  },
  data() {
    return {
      headers: [
        { text: "Code", value: "location_code", sortable: true },
        { text: "Team", value: "team.code", sortable: true },
        { text: "Longitude", value: "geo_longitude", sortable: true },
        { text: "Latitude", value: "geo_latitude", sortable: true },
        {
          text: "Address Text",
          value: "geo_address_text",
          sortable: true,
        },
        { text: "", value: "actions", sortable: false, align: "end" },
        //{ text: "", value: "data-table-actions", sortable: false, align: "end" }
      ],
    };
  },

  computed: {
    ...mapState("auth", ["userInfo",]),
    ...mapFields("location", [
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
    ...mapGetters("auth", ["getPermission"]),
    ...mapActions("location", [
      "getAll",
      "createEditShow",
      "removeShow",
      "closeCreateEdit",
    ]),
    ...mapActions("job", [
      "showJobEdit4Customer",
    ]),
    clickNewJobOnLocation( item) {
      this.showJobEdit4Customer({job: null,loc:item});

    },
  },
};
</script>
<style>
.location_code {
  display: block;
  max-width: 300px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>