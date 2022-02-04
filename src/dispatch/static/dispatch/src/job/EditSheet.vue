<template>
  <v-navigation-drawer v-model="showEditSheet" app clipped right width="800">
    <template v-slot:prepend>
      <v-list-item two-line>
        <v-list-item-content>
          <v-list-item-title class="title">{{ name }}</v-list-item-title>
          <v-list-item-subtitle
            >Last Updated - {{ updated_at | formatDate }}</v-list-item-subtitle
          >
        </v-list-item-content>

        <v-btn
          v-show="getPermission()('job.button.start')"
          icon
          color="primary"
          @click="
            updateJobLifeCycle({
              userEmail: userInfo.email,
              workerComment: 'NA',
              newStatus: 'Onsite_Started',
            })
          "
          :disabled="'Created' != life_cycle_status"
        >
          <v-icon>mdi-airplane-landing</v-icon>
        </v-btn>

        <v-btn
          v-show="getPermission()('job.button.finish')"
          icon
          color="primary"
          @click="
            updateJobLifeCycle({
              userEmail: userInfo.email,
              workerComment: 'NA',
              newStatus: 'Completed',
            })
          "
          :disabled="'Onsite_Started' != life_cycle_status"
        >
          <v-icon>mdi-airplane-takeoff</v-icon>
        </v-btn>

        <v-btn
          v-show="getPermission()('job.button.customer_approve')"
          icon
          color="primary"
          @click="
            updateJobLifeCycle({
              userEmail: userInfo.email,
              workerComment: 'NA',
              newStatus: 'Customer_Approved',
            })
          "
          :disabled="'Completed' != life_cycle_status"
        >
          <v-icon>mdi-check-circle</v-icon>
        </v-btn>

        <v-btn
          v-show="getPermission()('job.button.planner_approve')"
          icon
          color="primary"
          @click="
            updateJobLifeCycle({
              userEmail: userInfo.email,
              workerComment: 'NA',
              newStatus: 'Planner_Approved',
            })
          "
          :disabled="'Customer_Approved' != life_cycle_status"
        >
          <v-icon>mdi-credit-card-check</v-icon>
        </v-btn>

        <v-btn
          v-show="getPermission()('job.button.save')"
          icon
          color="primary"
          :loading="loading"
          @click="submitSaveLocal()"
          :disabled="['Worker'].includes(userInfo.role)"
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
      <v-tab key="flex_form" v-if="dataFormSchema != null">Flex Form</v-tab>
      <v-tab key="timeline">Timeline</v-tab>
    </v-tabs>
    <v-tabs-items v-model="tab">
      <v-tab-item key="jobs">
        <job-planner-details-tab />
      </v-tab-item>
      <v-tab-item key="flex_form">
        <JobFlexForm
          :formData="localFlexFormData"
          :formSchema="dataFormSchema"
        />
      </v-tab-item>

      <v-tab-item key="timeline">
        <job-timeline-tab />
      </v-tab-item>
    </v-tabs-items>
  </v-navigation-drawer>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { mapGetters } from "vuex";
import { mapState } from "vuex";

import { ValidationObserver } from "vee-validate";

import JobTimelineTab from "@/job/TimelineTab.vue";
import JobPlannerDetailsTab from "@/job/JobPlannerDetailsTab.vue";
import JobFlexForm from "@/components/FlexForm.vue";
import { cloneDeep } from "lodash";

export default {
  name: "JobEditSheet",

  components: {
    ValidationObserver,
    JobPlannerDetailsTab, //a
    JobTimelineTab,
    JobFlexForm,
  },
  data() {
    return {
      tab: null,
    };
  },
  mounted() {
    this.selectInventory();
  },
  computed: {
    ...mapState("auth", ["userInfo"]),
    ...mapFields("job", [
      "selected.id",
      "selected.name",
      "selected.description",
      "selected.flex_form_data",
      "selected.updated_at",
      "selected.team",
      "selected.loading",
      "selected.life_cycle_status",
      "dialogs.showEditSheet",
    ]),
    ...mapFields("org", ["selected.job_flex_form_schema"]),
    // 计算属性的 getter
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
    ...mapActions("job", [
      "setSelectedFormDataAndSave",
      "closeEditSheet",
      "updateJobLifeCycle",
    ]),
    ...mapActions("item_inventory", ["selectInventory"]),
    ...mapGetters("auth", ["getPermission"]),
    submitSaveLocal() {
      this.selectInventory();
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
