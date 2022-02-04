<template>
  <v-navigation-drawer v-model="showNewSheet" app clipped right width="800">
    <template v-slot:prepend>
      <v-list-item two-line>
        <v-list-item-content>
          <v-list-item-title class="title">New</v-list-item-title>
        </v-list-item-content>
        <v-btn icon color="primary" :loading="loading" @click="submitSaveLocal()">
          <v-icon>save</v-icon>
        </v-btn>
        <v-btn icon color="secondary" @click="closeNewSheet">
          <v-icon>close</v-icon>
        </v-btn>
      </v-list-item>
    </template>
    <v-tabs fixed-tabs v-model="tab">
      <v-tab key="details">Details</v-tab>
      <v-tab key="flex_form" v-if="dataFormSchema!=null">Flex Form</v-tab>
    </v-tabs>
    <v-tabs-items v-model="tab">
      <v-tab-item key="details">
        <job-planner-details-tab />
      </v-tab-item>
      <v-tab-item key="flex_form">
        <JobFlexForm :formData="localFlexFormData" :formSchema="dataFormSchema" />
      </v-tab-item>
    </v-tabs-items>
  </v-navigation-drawer>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
// import { ValidationObserver } from "vee-validate"
import JobPlannerDetailsTab from "@/job/JobPlannerDetailsTab.vue";
import JobFlexForm from "@/components/FlexForm.vue";
// import JobLocationTab from "@/job/JobLocationTab.vue"
import { cloneDeep } from "lodash";

export default {
  name: "JobNewSheet",

  components: {
    // ValidationObserver,
    // JobLocationTab,
    JobPlannerDetailsTab,
    JobFlexForm,
  },

  data() {
    return {
      tab: null,
    };
  },

  computed: {
    ...mapFields("job", [
      "selected.id",
      "selected.code",
      "selected.description",
      "selected.flex_form_data",
      "selected.loading",
      "dialogs.showNewSheet",
    ]),
    ...mapFields("org", ["selected.job_flex_form_schema"]),
    dataFormSchema: function () {
      return JSON.parse(JSON.stringify(this.job_flex_form_schema));
    },
    localFlexFormData: {
      get() {
        return cloneDeep(JSON.parse(JSON.stringify(this.flex_form_data)));
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },

  methods: {
    ...mapActions("job", ["setSelectedFormDataAndSave", "closeNewSheet"]),
    submitSaveLocal() {
      this.setSelectedFormDataAndSave({
        flex_form_data: Object.assign(
          cloneDeep(JSON.parse(JSON.stringify(this.flex_form_data))),
          this.localFlexFormData
        ),
      });
    },
  },
};
</script>
