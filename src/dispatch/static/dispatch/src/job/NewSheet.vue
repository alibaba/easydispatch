<template>
  <v-navigation-drawer v-model="showNewSheet" app clipped right width="800">
    <template v-slot:prepend>
      <v-list-item two-line>
        <v-list-item-content>
          <v-list-item-title class="title">New</v-list-item-title>
        </v-list-item-content>
        <v-btn icon color="primary" :loading="loading" @click="save()">
          <v-icon>save</v-icon>
        </v-btn>
        <v-btn icon color="secondary" @click="closeNewSheet">
          <v-icon>close</v-icon>
        </v-btn>
      </v-list-item>
    </template>
    <v-tabs fixed-tabs v-model="tab">
      <v-tab key="details">Details</v-tab>
      <v-tab key="flex_form">Flex Form</v-tab>
    </v-tabs>
    <v-tabs-items v-model="tab">
      <v-tab-item key="jobs">
        <job-planner-details-tab />
      </v-tab-item>
      <v-tab-item key="flex_form">
        <JobFlexForm :formData="localFlexFormData" :formSchema="formSchema" />
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

export default {
  name: "JobNewSheet",

  components: {
    // ValidationObserver,
    // JobLocationTab,
    JobPlannerDetailsTab,
    JobFlexForm
  },

  data() {
    return {
      tab: null,
      localFlexFormData: {},
      formSchema: {
        type: "object",
        properties: {
          job_schedule_type: {
            type: "string",
            title: "Job Type",
            description: "This affects timing, N=Normal, FS=Fixed Schedule.",
            enum: ["N", "FS"]
          },
          requested_min_level: {
            type: "number",
            title: "requested min level (integer)"
          },
          requested_skills: {
            type: "array",
            title: "requested_skills",
            items: {
              type: "string"
            }
          }
        }
      }
    };
  },

  computed: {
    ...mapFields("job", [
      "selected.id",
      "selected.code",
      "selected.description",
      "selected.loading",
      "dialogs.showNewSheet"
    ])
  },

  methods: {
    ...mapActions("job", ["save", "closeNewSheet"])
  }
};
</script>
