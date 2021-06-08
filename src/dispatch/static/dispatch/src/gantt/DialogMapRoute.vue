<template>
  <v-dialog
    v-model="dialogMapRouteVisible"
    persistent
    content
    content-class="centered-dialog"
    max-width="900px"
  >
    <v-card height="800px">
      <v-card-title>
        <span class="headline" v-if="job !== null"
          >Routing - {{ job.job_code }}</span
        >
        <v-spacer />

        <v-btn color="primary" dark class="ml-2" @click="closeDialogMapRoute()"
          >Close</v-btn
        >
      </v-card-title>
      <v-card-text>
        <v-container>
          <v-row>
            <v-col cols="12">
              <l-map
                ref="myRoutingMap"
                :zoom="zoom"
                :center="latLongCenter"
                style="height: 650px; width: 800px"
              >
                <l-tile-layer :url="osmUrl" :attribution="attribution" />
                <l-routing-machine :waypoints="latLongWayPoints" />
              </l-map>
            </v-col>
          </v-row>
        </v-container>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script>
// https://stackoverflow.com/questions/42816517/cant-load-leaflet-inside-vue-component/56114797
// height: 200px; width: 300px
import { mapGetters } from "vuex";
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
// https://juejin.im/post/5cc192976fb9a032092e8e0a#heading-1

import { LMap, LTileLayer } from "vue2-leaflet";
import "leaflet/dist/leaflet.css";

import LRoutingMachine from "./LRoutingMachine";

const attribution =
  '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a>';
const osmUrl = "http://{s}.tile.osm.org/{z}/{x}/{y}.png";

// https://stackoverflow.com/questions/49305901/leaflet-and-mapbox-in-modal-not-displaying-properly
// Comment out the below code to see the difference.

export default {
  name: "DialogMapRoute",

  components: { LMap, LTileLayer, LRoutingMachine },
  data() {
    return {
      zoom: 6,
      osmUrl,
      attribution,
    };
  },
  // https://cn.vuejs.org/v2/guide/components-edge-cases.html
  provide: function() {
    return {
      getMap: this.getMap,
    };
  },
  methods: {
    ...mapActions("gantt", ["closeDialogMapRoute"]),
    fetchData() {
      let filterOptions = {};
      return filterOptions;
    },
    getMap: function(found) {
      var vm = this;
      function checkForMap() {
        if (vm.$refs.myRoutingMap) {
          found(vm.$refs.myRoutingMap.mapObject);
        } else {
          setTimeout(checkForMap, 150);
        }
      }
      checkForMap();
    },
  },

  computed: {
    ...mapFields("gantt", [
      "dialogs.dialogMapRouteVisible",
      "selected.latLongWayPoints",
      "selected.latLongCenter",
      "selected.job",
    ]),
    ...mapGetters("gantt", ["getPlannerFilters"]),
  },
};
</script>
