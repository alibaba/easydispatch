<template>
  <v-container style="height: 600px; width: 800px">
    <l-map :zoom="zoom" :center="center" ref="myRoutingMap">
      <l-tile-layer :url="osmUrl" :attribution="attribution" />
      <l-routing-machine :waypoints="waypoints" />
    </l-map>
  </v-container>
</template>

<script>
// https://stackoverflow.com/questions/42816517/cant-load-leaflet-inside-vue-component/56114797
// height: 200px; width: 300px

import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";

import { LMap, LTileLayer } from "vue2-leaflet";
import "leaflet/dist/leaflet.css";

import LRoutingMachine from "./LRoutingMachine";

const attribution =
  '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors';
const osmUrl = "http://{s}.tile.osm.org/{z}/{x}/{y}.png";

// https://stackoverflow.com/questions/49305901/leaflet-and-mapbox-in-modal-not-displaying-properly
// Comment out the below code to see the difference.

export default {
  name: "MapDirect",

  components: { LMap, LTileLayer, LRoutingMachine },
  data() {
    return {
      zoom: 6,
      center: { lat: 38.7436056, lng: -5.2304153 },
      osmUrl,
      attribution,
      waypoints: [
        { lat: 38.7436056, lng: -9.2304153 },
        { lat: 38.7436056, lng: -0.131281 },
      ],
    };
  },

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
      "selected.latLongWayPoints",
      "dialogs.dialogMapRouteVisible",
    ]),
  },

  watch: {
    latLongWayPoints(newValue, oldValue) {
      // https://dev.to/viniciuskneves/watch-for-vuex-state-changes-2mgj
      console.log(`latLongWayPoints Updating from ${oldValue} to ${newValue}`);
      if (newValue) {
        console.log(newValue[0], newValue[1]);
      }

      // Do whatever makes sense now
    },
  },
};
</script>
