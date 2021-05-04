<template>
  <v-container grid-list-md>
    <v-layout wrap>
      <v-flex xs12>
        <business-hours
          :days="businessDays"
          :hourFormat24="true"
          @updated-hours="saveFunc"
        ></business-hours>
      </v-flex>
    </v-layout>
  </v-container>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import BusinessHours from "vue-business-hours";

export default {
  name: "WorkerTabBusinessHour",

  components: {
    BusinessHours
  },
  props: {
    businessDays: {
      type: Object,
      default: function() {
        return {};
      }
    },
    saveFunc: {
      type: Function,
      default: function() {
        return this.defaultSaveFunc;
      }
    }
  },
  data() {
    return {
      //changedInside: false,
      days: {
        sunday: [
          {
            open: "",
            close: "",
            id: "5ca5578b0c5c7",
            isOpen: false
          }
        ],
        monday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5d1",
            isOpen: true
          }
        ],
        tuesday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5d8",
            isOpen: true
          }
        ],
        wednesday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5df",
            isOpen: true
          }
        ],
        thursday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5e6",
            isOpen: true
          }
        ],
        friday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5ec",
            isOpen: true
          },
          {
            open: "1900",
            close: "2200",
            id: "5ca5578b0c5f2",
            isOpen: true
          }
        ],
        saturday: [
          {
            open: "24hrs",
            close: "24hrs",
            id: "5ca5578b0c5f8",
            isOpen: true
          }
        ]
      }
    };
  },
  computed: {
    ...mapFields("worker", [
      "selected.name",
      "selected.code",
      "selected.company",
      "selected.terms",
      "selected.job_priorities",
      "selected.job_types",
      "selected.id",
      "selected.team",
      "selected.loading",
      "selected.flex_form_data",
      "selected.business_hour",
      "dialogs.showCreateEdit"
    ])
  }
};
</script>
