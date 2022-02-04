<template>
  <div>
    <slot></slot>
  </div>
</template>

<script>
// import L from "leaflet"
// https://github.com/jurb/vue2-leaflet-heatmap/issues/1
// It indicates mismatching leaflet versions.
import { findRealParent, L } from "vue2-leaflet";
import { mapFields } from "vuex-map-fields";
import { IRouter, IGeocoder, LineOptions } from "leaflet-routing-machine";

import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl,
  iconUrl,
  shadowUrl,
});

const props = {
  selected_marker: {
    type: Array,
    required: true,
  },
  visible: {
    type: Boolean,
    default: false,
  },
  waypoints: {
    type: Array,
    required: true,
  },
  router: {
    type: IRouter,
  },
  plan: {
    type: L.Routing.Plan,
  },
  geocoder: {
    type: IGeocoder,
  },
  fitSelectedRoutes: {
    type: [String, Boolean],
    default: "smart",
  },
  lineOptions: {
    type: LineOptions,
  },
  routeLine: {
    type: Function,
  },
  autoRoute: {
    type: Boolean,
    default: true,
  },
  routeWhileDragging: {
    type: Boolean,
    default: false,
  },
  routeDragInterval: {
    type: Number,
    default: 500,
  },
  waypointMode: {
    type: String,
    default: "connect",
  },
  useZoomParameter: {
    type: Boolean,
    default: false,
  },
  showAlternatives: {
    type: Boolean,
    default: false,
  },
  altLineOptions: {
    type: LineOptions,
  },
  createMarker: {
    type: Function,
    default: function (i, wp, nWps) {
      return false;
    },
  },
  collapsible: {
    type: Boolean,
    default: true,
  },
};

export default {
  props,
  inject: ["getMap"],
  name: "LRoutingMachine",
  data() {
    return {
      parentContainer: null,
      ready: false,
      layer: null,
    };
  },
  mounted() {
    console.log(
      "LRoutingMachine mounted, routing waypoints to: ",
      this.waypoints
    );
    this.parentContainer = findRealParent(this.$parent);
    //this.add()
    this.ready = true;

    var vm = this;
    vm.getMap(function (mapObject) {
      vm.add2MapObject(mapObject);
    });
  },

  beforeDestroy() {
    return this.layer ? this.layer.remove() : null;
  },
  watch: {
    waypoints: function (newVal, oldVal) {
      // watch it
      console.log(
        "LRoutingMachine waypoints changed to: ",
        newVal,
        " | was: ",
        oldVal
      );
      this.delete();
      //this.add()
      if (newVal) {
        var vm = this;
        vm.getMap(function (mapObject) {
          vm.add2MapObject(mapObject);
        });
      }
    },
    selected_marker: function (newVal, oldVal) {
      // watch it
      if (newVal.indexOf("start") < 0 || newVal.indexOf("end") < 0) {
        this.delete();
      }
    },
  },
  computed: {
    ...mapFields("live_map", ["serviceUrl"]),
  },
  methods: {
    add2MapObject(mapObject) {
      if (this.parentContainer._isMounted && this.waypoints) {
        const {
          waypoints,
          fitSelectedRoutes,
          autoRoute,
          routeWhileDragging,
          routeDragInterval,
          waypointMode,
          useZoomParameter,
          showAlternatives,
          createMarker,
          collapsible,
        } = this;

        const options = {
          // serviceUrl: "https://kerrypoc.dispatch.kandbox.com/route/v1",
          // serviceUrl: "https://londondemo1.dispatch.kandbox.com/route/v1",
          // serviceUrl: "https://routing.openstreetmap.de/routed-bike/route/v1",
          // serviceUrl: "http://127.0.0.1:5000/route/v1",
          // serviceUrl: "http://router.project-osrm.org/route/v1",
          serviceUrl: this.serviceUrl,
          waypoints,
          fitSelectedRoutes,
          autoRoute,
          routeWhileDragging,
          routeDragInterval,
          waypointMode,
          useZoomParameter,
          showAlternatives,
          createMarker,
          collapsible,
          lineOptions: {
            styles: [
              { color: "black", opacity: 0.15, weight: 9 },
              { color: "white", opacity: 0.8, weight: 6 },
              { color: "green", opacity: 1, weight: 2 },
            ],
            addWaypoints: false,
          },
        };
        // mapObject.invalidateSize();
        // mapObject.setView(global_center_latlong, 8);

        const routingLayer = L.Routing.control(options);
        routingLayer.addTo(mapObject);
        this.layer = routingLayer;

        // mapObject.setView(
        //   new L.LatLng(global_center_latlong[0], global_center_latlong[1]),
        //   8
        // );

        // mapObject.flyTo(global_center_latlong, 8);
        mapObject.invalidateSize();
        // var global_center_latlong = [
        //   (options.waypoints[0].lat + options.waypoints[1].lat) / 2,
        //   (options.waypoints[0].lng + options.waypoints[1].lng) / 2 + 0.2,
        // ];
        // console.log(
        //   `latLongWayPoints Updating, resized to ${global_center_latlong}`
        // );
      }
    },
    delete() {
      const { mapObject } = this.parentContainer;
      if (this.layer) {
        mapObject.removeControl(this.layer);
        this.layer = null;
      }
    },
    // refresh() {
    //   this.delete();
    //   this.add();
    // },
  },
};
</script>

<style>
@import "../../node_modules/leaflet-routing-machine/dist/leaflet-routing-machine.css";
</style>
