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
                :center="center"
                style="height: 400px; width: 800px"
              >
                <l-tile-layer :url="osmUrl" :attribution="attribution" />
                <l-routing-machine :waypoints="waypoints" />
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
  '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors';
const osmUrl = "http://{s}.tile.osm.org/{z}/{x}/{y}.png";

// https://stackoverflow.com/questions/49305901/leaflet-and-mapbox-in-modal-not-displaying-properly
// Comment out the below code to see the difference.

export default {
  name: "DialogMapRoute",

  components: { LMap, LTileLayer, LRoutingMachine },
  data() {
    return {
      zoom: 6,
      center: { lat: 38.7436056, lng: -5.2304153 },
      osmUrl,
      attribution,
      waypoints: [
        { lat: 38.7436056, lng: -9.2304153 },
        { lat: 38.7436056, lng: -0.131281 }
      ]
    };
  },
  // https://cn.vuejs.org/v2/guide/components-edge-cases.html
  provide: function() {
    return {
      getMap: this.getMap
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
    }
  },

  computed: {
    ...mapFields("gantt", [
      "dialogs.dialogMapRouteVisible",
      "selected.latLongRouteArray",
      "selected.job"
    ]),
    ...mapGetters("gantt", [
      "getPlannerFilters"
      // ...
    ])
  },

  watch: {
    latLongRouteArray(newValue, oldValue) {
      // https://dev.to/viniciuskneves/watch-for-vuex-state-changes-2mgj
      console.log(`latLongRouteArray Updating from ${oldValue} to ${newValue}`);
      if (newValue) {
        console.log(newValue[0], newValue[1]);
        let from_latlng = newValue[0];
        let to_latlng = newValue[1];

        this.center.lat = (from_latlng[0] + to_latlng[0]) / 2;
        this.center.lng = (from_latlng[1] + to_latlng[1]) / 2 + 0.2;

        this.waypoints = [
          { lat: from_latlng[0], lng: from_latlng[1] },
          { lat: to_latlng[0], lng: to_latlng[1] }
          //	{ lat: 38.7436056, lng: -9.2304153 },
          // { lat: 38.7436056, lng: -0.131281 }
        ];

        //global_map_obj.invalidateSize()
        //global_map_obj.setView(global_center_latlong, 10)
        // call show mutation.
        /*

        // Do whatever makes sense now
        */
      }
    }
  }
};
</script>
