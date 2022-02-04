<template>
  <ValidationObserver>
    <v-navigation-drawer v-model="showCreateEdit" app clipped right width="600">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
            <v-list-item-title v-else class="title">New</v-list-item-title>
            <v-list-item-subtitle>Worker</v-list-item-subtitle>
          </v-list-item-content>
          <v-btn icon color="primary" :loading="loading" @click="submitSaveLocal()">
            <v-icon>save</v-icon>
          </v-btn>
          <v-btn icon color="secondary" @click="closeCreateEdit()">
            <v-icon>close</v-icon>
          </v-btn>
        </v-list-item>
      </template>
      <v-tabs fixed-tabs v-model="tab">
        <v-tab key="workers">WorkerDetail</v-tab>
        <v-tab key="flex_form" v-if="localFlexFormData!=null">FlexForm</v-tab>
        <v-tab key="business_hour">BusinessHour</v-tab>
        <v-tab key="history">History</v-tab>
      </v-tabs>
      <v-tabs-items v-model="tab">
        <v-tab-item key="workers">
          <worker-details-tab />
        </v-tab-item>
        <v-tab-item key="flex_form">
          <worker-flex-form :saveFunc="saveFormLocal" :formData="localFlexFormData" />
        </v-tab-item>
        <v-tab-item key="business_hour">
          <worker-tab-business-hour :saveFunc="updatedHours" :businessDays="business_hour__local" />
        </v-tab-item>
        <v-tab-item key="history">
          <JobMap />
        </v-tab-item>
      </v-tabs-items>
    </v-navigation-drawer>
  </ValidationObserver>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions, mapMutations } from "vuex";
import { ValidationObserver, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import WorkerDetailsTab from "@/worker/WorkerDetailsTab.vue";
import WorkerFlexForm from "@/worker/WorkerFlexForm.vue";
import WorkerTabBusinessHour from "@/worker/WorkerTabBusinessHour.vue";
// import LocationNewEditSheet from "@/location/LocationNewEditSheet.vue"
import JobMap from "./JobMap";
import { cloneDeep } from "lodash";

extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "WorkerNewEditSheet",

  components: {
    ValidationObserver,
    WorkerDetailsTab,
    WorkerTabBusinessHour,
    WorkerFlexForm,
    JobMap,
    // LocationNewEditSheet
  },
  data() {
    return {
      tab: null,
      // localFlexFormData: {},
      business_hour__local: {
        sunday: [
          {
            open: "",
            close: "",
            id: "5ca5578b0c5c7",
            isOpen: false,
          },
        ],
        monday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5d1",
            isOpen: true,
          },
        ],
        tuesday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5d8",
            isOpen: true,
          },
        ],
        wednesday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5df",
            isOpen: true,
          },
        ],
        thursday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5e6",
            isOpen: true,
          },
        ],
        friday: [
          {
            open: "0800",
            close: "1700",
            id: "5ca5578b0c5ec",
            isOpen: true,
          },
        ],
        saturday: [
          {
            open: "",
            close: "",
            id: "5ca5578b0c5f8",
            isOpen: false,
          },
        ],
      },
    };
  },

  computed: {
    ...mapFields("worker", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.flex_form_data",
      "selected.business_hour",
      "selected.loading",
      "dialogs.showCreateEdit",
    ]),
    localFlexFormData: {
      get() {
        return cloneDeep(JSON.parse(JSON.stringify(this.flex_form_data)));
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },
  mounted() {
    this.selectInventory();
  },
  watch: {
    business_hour: function (newVal, oldVal) {
      if (newVal) {
        this.business_hour__local = JSON.parse(JSON.stringify(this.newVal));
      }
    },
  },
  methods: {
    ...mapMutations("worker", ["SET_SELECTED_BUSINESS_HOUR"]),
    ...mapActions("worker", [
      "save",
      "closeCreateEdit",
      "setSelectedFormDataAndSave",
    ]),
    //...mapActions("worker", [""])
    ...mapActions("item_inventory", ["selectInventory"]),
    submitSaveLocal() {
      this.selectInventory();
      this.setSelectedFormDataAndSave({
        flex_form_data: Object.assign(
          cloneDeep(JSON.parse(JSON.stringify(this.flex_form_data))),
          this.localFlexFormData
        ),
      });
    },
    updatedHours: function (value) {
      this.SET_SELECTED_BUSINESS_HOUR(value);
    },
    saveFormLocal(value) {
      this.localFlexFormData = value;
    },
  },
};
</script>
