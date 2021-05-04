<template>
  <div style="display: none">
    <slot v-if="ready"></slot>
  </div>
</template>

<script>
// import L from "leaflet"
// https://github.com/jurb/vue2-leaflet-heatmap/issues/1
// It indicates mismatching leaflet versions.
import { findRealParent, L } from "vue2-leaflet";
import { IRouter, IGeocoder, LineOptions } from "leaflet-routing-machine";

import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl,
  iconUrl,
  shadowUrl
});

const props = {
  visible: {
    type: Boolean,
    default: true
  },
  waypoints: {
    type: Array,
    required: true
  },
  router: {
    type: IRouter
  },
  plan: {
    type: L.Routing.Plan
  },
  geocoder: {
    type: IGeocoder
  },
  fitSelectedRoutes: {
    type: [String, Boolean],
    default: "smart"
  },
  lineOptions: {
    type: LineOptions
  },
  routeLine: {
    type: Function
  },
  autoRoute: {
    type: Boolean,
    default: true
  },
  routeWhileDragging: {
    type: Boolean,
    default: false
  },
  routeDragInterval: {
    type: Number,
    default: 500
  },
  waypointMode: {
    type: String,
    default: "connect"
  },
  useZoomParameter: {
    type: Boolean,
    default: false
  },
  showAlternatives: {
    type: Boolean,
    default: false
  },
  altLineOptions: {
    type: LineOptions
  }
};

// const optionTestNames = [
//   'router',
//   'plan',
//   'geocoder',
//   'lineOptions',
//   'routeLine',
//   'altLineOptions'
// ]

export default {
  props,
  inject: ["getMap"],
  name: "LRoutingMachine",
  data() {
    return {
      parentContainer: null,
      ready: false,
      layer: null
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
    vm.getMap(function(mapObject) {
      vm.add2MapObject(mapObject);
    });
  },

  beforeDestroy() {
    return this.layer ? this.layer.remove() : null;
  },
  watch: {
    waypoints: function(newVal, oldVal) {
      // watch it
      console.log(
        "LRoutingMachine waypoints changed to: ",
        newVal,
        " | was: ",
        oldVal
      );
      this.delete();
      //this.add()
      var vm = this;
      vm.getMap(function(mapObject) {
        vm.add2MapObject(mapObject);
      });
    }
  },
  methods: {
    add() {
      if (this.parentContainer._isMounted) {
        const {
          waypoints,
          fitSelectedRoutes,
          autoRoute,
          routeWhileDragging,
          routeDragInterval,
          waypointMode,
          useZoomParameter,
          showAlternatives
        } = this;

        const options = {
          waypoints,
          fitSelectedRoutes,
          autoRoute,
          routeWhileDragging,
          routeDragInterval,
          waypointMode,
          useZoomParameter,
          showAlternatives
        };

        const routingLayer = L.Routing.control(options);
        // routingLayer.addTo(this.parentContainer.$refs.myRoutingMap.mapObject)
        const { mapObject } = this.parentContainer;
        routingLayer.addTo(mapObject);
        this.layer = routingLayer;
      }
    },

    add2MapObject(mapObject) {
      if (this.parentContainer._isMounted) {
        const {
          waypoints,
          fitSelectedRoutes,
          autoRoute,
          routeWhileDragging,
          routeDragInterval,
          waypointMode,
          useZoomParameter,
          showAlternatives
        } = this;

        const options = {
          waypoints,
          fitSelectedRoutes,
          autoRoute,
          routeWhileDragging,
          routeDragInterval,
          waypointMode,
          useZoomParameter,
          showAlternatives
        };

        const routingLayer = L.Routing.control(options);
        routingLayer.addTo(mapObject);
        this.layer = routingLayer;

        var global_center_latlong = [
          (options.waypoints[0].lat + options.waypoints[1].lat) / 2,
          (options.waypoints[0].lng + options.waypoints[1].lng) / 2 + 0.2
        ];

        mapObject.invalidateSize();
        console.log(
          `latLongRouteArray Updating, resized to ${global_center_latlong}`
        );
        mapObject.setView(global_center_latlong, 10);
      }
    },
    delete() {
      const { mapObject } = this.parentContainer;
      if (this.layer) {
        mapObject.removeControl(this.layer);
        this.layer = null;
      }
    },
    refresh() {
      this.delete();
      this.add();
    }
  }
};
</script>

<style>
@import "../../node_modules/leaflet-routing-machine/dist/leaflet-routing-machine.css";
</style>
