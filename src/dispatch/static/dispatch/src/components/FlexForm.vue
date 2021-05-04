<template>
  <v-container grid-list-md>
    <v-form v-model="valid">
      <v-jsf v-model="formData" :schema="formSchema" :options="formOptions" />
    </v-form>
  </v-container>
</template>

<script>
//import { mapFields } from "vuex-map-fields"
//import { mapActions } from "vuex"
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
    VJsf
  },
  methods: {},

  props: {
    formSchema: {
      type: Object,
      default: function() {
        return {
          type: "object",
          properties: {
            level: {
              type: "number",
              title: "requested min level (integer)"
            },
            skills: {
              type: "array",
              title: "requested_skills",
              items: {
                type: "string"
              }
            }
          }
        };
      }
    },
    formData: {
      type: Object,
      default: function() {
        return {};
      }
    }
  },

  data() {
    return {
      //changedInside: false,
      valid: null,
      formOptions: {}

      //formData__OLD: { level: 1, skills: ["skill_1"] }
      /**/
    };
  } /*,
  watch___1: {
    formData: function(newVal, oldVal) {
      // watch it
      console.log("formData changed: ", newVal, " | was: ", oldVal)
      // this.setSelectedFormData(newVal)
      this.formData__OLD = JSON.parse(JSON.stringify(newVal))
      if (!this.changedInside) {
        console.log("formData changed, and set  ")
      } else {
        console.log("formData changed, but not skipped")
        this.changedInside = false
      }
    },
    formData__OLD: {
      // This will let Vue know to look inside the array
      deep: true,

      // We have to move our method to a handler field
      handler() {
        //return
        console.log("formData__OLD changed: ", this.changedInside, this.formData__OLD)
        //this.$store.dispatch("worker/setSelected", { flex_form_data: this.formData })
        //this.setSelected({ flex_form_data: this.formData })
        //if (true) {
        console.log("formData__OLD submited: ", this.changedInside, this.formData__OLD)
        this.saveFunc(this.formData__OLD)
        this.changedInside = true
        //}
      }
    }
  },
  computed: {

    ...mapFields("worker", [
      "selected.name",
      "selected.code",
      "selected.flex_form_data",
      "selected.id"
    ]),
    worker_form_data_mapped: {
      get() {
        // return JSON.parse(JSON.stringify(this.flex_form_data))
        console.log("setSelectedFormData selected: ", this.flex_form_data)
        // this.formData__OLD = JSON.parse(JSON.stringify(this.flex_form_data))
        return this.formData__OLD
      },
      set(value) {
        //this.$store.commit("setSelectedFormData", value)

        console.log("setSelectedFormData changed: ", value)
        //this.formData__OLD = value
        //this.setSelectedFormData(value)
        //const a = JSON.parse(JSON.stringify(value))
        //this.saveFunc(a)
      }

  } }*/
};
</script>
