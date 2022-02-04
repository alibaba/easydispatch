<template>
  <v-container grid-list-md>
    <v-form v-model="valid">
      <v-jsf v-model="formData" :schema="dataFormSchema" :options="formOptions" />
    </v-form>
  </v-container>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
// https://www.npmjs.com/package/@koumoul/vuetify-jsonschema-form

import Vue from "vue";
import Vuetify from "vuetify";
import "vuetify/dist/vuetify.min.css";

import VJsf from "@koumoul/vjsf";

Vue.use(Vuetify);
Vue.component("VJsf", VJsf);
import "@koumoul/vjsf/dist/main.css";

// load third-party dependencies (markdown-it, vuedraggable)
// you can also load them separately based on your needs
//import "@koumoul/vjsf/dist/third-party.js"

export default {
  name: "WorkerFlexForm",

  components: {
    VJsf,
  },
  methods: {
    defaultSaveFunc() {
      console.log("default saved. empty!");
    },
  },

  props: {
    formData: {
      type: Object,
      default: function () {
        return {};
      },
    },
    saveFunc: {
      type: Function,
      default: function () {
        return this.defaultSaveFunc;
      },
    },
  },

  data() {
    return {
      //changedInside: false,
      valid: null,
      formOptions: {},
    };
  },

  computed: {
    ...mapFields("org", ["selected.worker_flex_form_schema"]),
    dataFormSchema: function () {
      return JSON.parse(JSON.stringify(this.worker_flex_form_schema));
    },
  },
};
</script>
