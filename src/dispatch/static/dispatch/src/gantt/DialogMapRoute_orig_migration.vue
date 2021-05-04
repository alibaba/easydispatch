<template>
  <v-dialog
    v-model="dialogMapRouteVisible"
    persistent
    content
    content-class="centered-dialog"
    max-width="600px"
  >
    <v-card>
      <v-card-title>
        <span class="headline">Routing - Duan</span>
        <v-spacer />
        <v-btn color="primary" dark class="ml-2" @click="closeDialogMapRoute()"
          >Close</v-btn
        >
      </v-card-title>
      <v-card-text>
        <v-container>
          <v-row>
            <v-col cols="12">
              <v-text-field label="Email current date:"></v-text-field>
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12">
              <div id="map_container"></div>
            </v-col>
          </v-row>
        </v-container>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue darken-1" text @click="dialog = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
// https://stackoverflow.com/questions/42816517/cant-load-leaflet-inside-vue-component/56114797

import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
// https://juejin.im/post/5cc192976fb9a032092e8e0a#heading-1
import "leaflet/dist/leaflet.css";
import L from "leaflet";
var global_map_obj = null;
var routingControl = null;
var global_center_latlong = null;

function global_setup_map() {
  global_map_obj = L.map("map_container");
  global_map_obj.invalidateSize();

  // http://localhost:5008/tile/{z}/{x}/{y}.png', { //
  // https://{s}.tile.osm.org/{z}/{x}/{y}.png', {
  // http://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}', { //
  L.tileLayer(
    "http://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}",
    {
      //
      attribution: "openstreetmap.org"
    }
  ).addTo(global_map_obj);

  global_center_latlong = null;
  routingControl = null;
}

// var routingControl = null;

// https://github.com/Leaflet/Leaflet.Icon.Glyph

var addRoutingControl = function(waypoints) {
  if (routingControl != null) removeRoutingControl();

  routingControl = L.Routing.control({
    waypoints: waypoints,
    createMarker: function(i, start, n) {
      var marker_icon = null;
      if (i == 0) {
        // This is the first marker, indicating start
        marker_icon = L.icon.glyph({
          prefix: "",
          glyph: "S"
        });
      } else if (i == n - 1) {
        //This is the last marker indicating destination
        marker_icon = L.icon.glyph({
          prefix: "",
          glyph: "E"
        });
      }
      var marker = L.marker(start.latLng, {
        draggable: true,
        bounceOnAdd: false,
        bounceOnAddOptions: {
          duration: 1000,
          height: 800,
          function() {
            //bindPopup(myPopup).openOn(global_map_obj)
          }
        },
        icon: marker_icon
      });
      return marker;
    }
  }).addTo(global_map_obj);
  L.Routing.errorControl(routingControl).addTo(global_map_obj);
};

var removeRoutingControl = function() {
  if (routingControl != null) {
    global_map_obj.removeControl(routingControl);
    routingControl = null;
  }
};

var show_job_route = function(from_latlng, to_latlng) {
  global_center_latlong = [
    (from_latlng[0] + to_latlng[0]) / 2,
    (from_latlng[1] + to_latlng[1]) / 2 + 0.2
  ];
  removeRoutingControl();
  addRoutingControl([
    L.latLng(from_latlng[0], from_latlng[1]),
    L.latLng(to_latlng[0], to_latlng[1])
    //		L.latLng( 3.5245169,	101.90809300000001 ),
    //L.latLng(3.2662035,	101.64786009999999)
  ]);
  global_map_obj.invalidateSize();
  global_map_obj.setView(global_center_latlong, 10);
  // call show mutation.
};

// https://stackoverflow.com/questions/49305901/leaflet-and-mapbox-in-modal-not-displaying-properly
// Comment out the below code to see the difference.

export default {
  name: "DialogMapRoute",

  methods: {
    ...mapActions("gantt", ["closeDialogMapRoute"]),
    fetchData() {
      let filterOptions = {};
      return filterOptions;
    }
  },

  components: {
    // WorkerCombobox,
  },

  data() {
    return {
      map_obj: null
    };
  },

  mounted() {
    global_setup_map();
    this.map_obj = global_map_obj;
  },
  computed: {
    ...mapFields("gantt", [
      "selected.latLongRouteArray",
      "dialogs.dialogMapRouteVisible"
    ])
  },

  watch: {
    latLongRouteArray(newValue, oldValue) {
      // https://dev.to/viniciuskneves/watch-for-vuex-state-changes-2mgj
      console.log(`latLongRouteArray Updating from ${oldValue} to ${newValue}`);
      if (newValue) {
        show_job_route(newValue[0], newValue[1]);
      }

      // Do whatever makes sense now
    }
  }
};
</script>
