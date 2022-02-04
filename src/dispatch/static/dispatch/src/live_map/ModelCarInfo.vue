<template>
  <v-dialog
    v-model="dispatch_car_model_visible"
    persistent
    content
    content-class="centered-dialog"
    max-width="300px"
    style="z-index:  9999;"
  >
    <v-card class="mx-auto" tile>
      <v-list flat>
        <v-subheader>
          <span class="headline">dispatch car</span>
          <v-spacer />
          <v-btn
            class="ma-1"
            color="error"
            x-small
            elevation="2"
            plain
            @click="dispatch_car(!dispatch_car_model_visible)"
          >Close</v-btn>
        </v-subheader>
        <v-list-item v-for="(item, i) in car_list" :key="i">
          <v-list-item-content>
            <v-list-item-title v-text="item.car_number"></v-list-item-title>
          </v-list-item-content>
          <v-list-item-content>
            <v-list-item-title v-text="item.address_to"></v-list-item-title>
          </v-list-item-content>
        </v-list-item>
      </v-list>
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
  name: "ModelCarInfo",

  components: { LMap, LTileLayer, LRoutingMachine },
  data() {
    return {
      zoom: 6,
      osmUrl,
      attribution,
    };
  },
  // https://cn.vuejs.org/v2/guide/components-edge-cases.html
  provide: function () {
    return {
      getMap: this.getMap,
    };
  },
  computed: {
    ...mapFields("live_map", [
      "dispatch_car.dispatch_car_model_visible",
      "dispatch_car.car_list",
    ]),
  },
  methods: {
    ...mapActions("live_map", ["dispatch_car"]),
  },
};
</script>
