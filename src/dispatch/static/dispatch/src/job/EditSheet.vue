<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-navigation-drawer v-model="showEditSheet" app clipped right width="800">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title class="title">{{ name }}</v-list-item-title>
            <v-list-item-subtitle
              >Reported - {{ updated_at | formatDate }}</v-list-item-subtitle
            >
          </v-list-item-content>
          <v-btn
            icon
            color="primary"
            :loading="loading"
            :disabled="invalid || !validated"
            @click="submitSaveWithFormValue()"
          >
            <v-icon>save</v-icon>
          </v-btn>
          <v-btn icon color="secondary" @click="closeEditSheet">
            <v-icon>close</v-icon>
          </v-btn>
        </v-list-item>
      </template>
      <v-tabs fixed-tabs v-model="tab">
        <v-tab key="jobs">Job Detail</v-tab>
        <v-tab key="flex_form">Flex Form</v-tab>
        <v-tab key="participants">Participants</v-tab>
        <v-tab key="timeline">Timeline</v-tab>
      </v-tabs>
      <v-tabs-items v-model="tab">
        <v-tab-item key="jobs">
          <job-planner-details-tab />
        </v-tab-item>
        <v-tab-item key="flex_form">
          <JobFlexForm :formData="localFlexFormData" :formSchema="formSchema" />
        </v-tab-item>
        <v-tab-item key="participants">
          <job-participants-tab />
        </v-tab-item>
        <v-tab-item key="timeline">
          <job-timeline-tab />
        </v-tab-item>
      </v-tabs-items>
    </v-navigation-drawer>
  </ValidationObserver>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { ValidationObserver } from "vee-validate";

import JobTimelineTab from "@/job/TimelineTab.vue";
import JobPlannerDetailsTab from "@/job/JobPlannerDetailsTab.vue";
import JobFlexForm from "@/components/FlexForm.vue";

export default {
  name: "JobEditSheet",

  components: {
    ValidationObserver,
    JobPlannerDetailsTab, //a
    JobTimelineTab,
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
  watch: {
    flex_form_data: function(newVal) {
      // watch it
      console.log("flex_form_data changed: ", newVal);
      // this.setSelectedFormData(newVal)
      //if (this.tab == 1) {
      this.localFlexFormData = JSON.parse(JSON.stringify(newVal));
      //}
    }
  },
  computed: {
    ...mapFields("job", [
      "selected.id",
      "selected.name",
      "selected.description",
      "selected.flex_form_data",
      "selected.updated_at",
      "selected.team",
      "selected.loading",
      "dialogs.showEditSheet"
    ])
  },

  methods: {
    ...mapActions("job", ["setSelectedFormDataAndSave", "closeEditSheet"]),
    submitSaveWithFormValue() {
      this.setSelectedFormDataAndSave(this.localFlexFormData);
    }
  }
};
</script>
