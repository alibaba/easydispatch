<template>
  <v-app>
    <v-card max-width="500" class="mx-auto edit_page">
      <v-toolbar dark>
        <v-toolbar-title>{{code}}</v-toolbar-title>

        <v-spacer></v-spacer>

        <v-scale-transition>
          <v-btn icon color="primary" @click="submitSaveLocal()">
            <v-icon>save</v-icon>
          </v-btn>
        </v-scale-transition>
        <v-scale-transition>
          <v-btn icon color="white" @click="close">
            <v-icon>close</v-icon>
          </v-btn>
        </v-scale-transition>
      </v-toolbar>

      <v-container grid-list-md>
        <v-layout wrap>
          <v-flex xs6>
            <ValidationProvider name="Job Code" rules="required" immediate>
              <v-text-field
                v-model="code"
                slot-scope="{ errors, valid }"
                :error-messages="errors"
                :success="valid"
                label="Job Code"
                hint="Title of Job."
                clearable
                required
              />
            </ValidationProvider>
          </v-flex>

          <v-flex xs6>
            <v-text-field v-model="name" label="Job Name" hint="Job Name" clearable />
          </v-flex>
          <v-flex xs12>
            <span class="subtitle-2">Requested As:</span>
          </v-flex>

          <v-flex xs12>
            <v-row>
              <v-col cols="6">
                <date-picker-menu v-model="requested_start_datetime"></date-picker-menu>
              </v-col>
              <v-col cols="6">
                <time-picker-menu v-model="requested_start_datetime"></time-picker-menu>
              </v-col>
            </v-row>
          </v-flex>
          <v-flex xs6>
            <ValidationProvider name="Requested Minutes" rules="required" immediate>
              <v-text-field
                v-model="requested_duration_minutes"
                slot-scope="{ errors, valid }"
                label="Requested Minutes"
                :error-messages="errors"
                :success="valid"
                type="number"
                hint="Enter an value indicating number of Minutes, i.e. 120 for 2 hours."
                clearable
                required
              />
            </ValidationProvider>
          </v-flex>
          <v-flex xs6>
            <ValidationProvider name="Planning Status" rules="required" immediate>
              <v-select
                v-model="planning_status"
                :items="planning_status_items"
                label="Planning Status"
                slot-scope="{ errors, valid }"
                :error-messages="errors"
                :success="valid"
                hint="Planning Status(U, I, P, F)"
                clearable
                required
                prepend-icon="mdi-calendar-range "
              ></v-select>
            </ValidationProvider>
          </v-flex>
          <v-flex xs12>
            <v-combobox
              v-model="requested_skills"
              :items="team_requested_skills"
              label="requested skills"
              multiple
              chips
              clearable
              deletable-chips
            ></v-combobox>
          </v-flex>
          <InventoryCombobox
            v-model="requested_items_conbobox"
            v-bind:items="select_inventory_copy"
            label="requested items"
          />
          <v-flex xs12>
            <span class="subtitle-2">Scheduled To:</span>
          </v-flex>
          <v-flex xs12>
            <v-row>
              <v-col cols="6">
                <date-picker-menu v-model="scheduled_start_datetime"></date-picker-menu>
              </v-col>
              <v-col cols="6">
                <time-picker-menu v-model="scheduled_start_datetime"></time-picker-menu>
              </v-col>
            </v-row>
          </v-flex>
          <v-flex xs6>
            <v-text-field
              v-model="scheduled_duration_minutes"
              label="Scheduled Minutes"
              type="number"
              hint="Enter an Scheduled Minutes."
              clearable
            />
          </v-flex>

          <v-flex xs12>
            <v-textarea
              v-model="description"
              label="Description"
              hint="Description of job."
              clearable
            />
          </v-flex>

          <v-flex xs12>
            <v-switch
              v-model="auto_planning"
              hint="Each plugin type can only ever have one enabled plugin. Existing enabled plugins will be de-activated."
              :label="
            auto_planning ? 'Dispatch Automatically' : 'Dispatch Manually'
          "
            />
          </v-flex>
        </v-layout>
        <Snackbar />
      </v-container>
    </v-card>
  </v-app>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import WorkerSelect from "@/worker/WorkerSelect.vue";
import Snackbar from "@/components/Snackbar.vue";
import DatePickerMenu from "@/components/DatePickerMenu.vue";
import TimePickerMenu from "@/components/TimePickerMenu.vue";
import TagFilterCombobox from "@/tag/TagFilterCombobox.vue";
import WorkerCombo from "@/worker/WorkerCombobox.vue"; // ee-eslint-disable-line no-unused-vars
import InventoryCombobox from "@/item_inventory/InventoryCombobox.vue";
import { cloneDeep } from "lodash";

import { mapActions, mapMutations } from "vuex";
extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "JobPlannerDetailsTab",

  props: ["jobId", "token"],
  components: {
    ValidationProvider,
    WorkerSelect,
    WorkerCombo,
    TagFilterCombobox,
    TimePickerMenu,
    DatePickerMenu,
    InventoryCombobox,
    Snackbar,
  },

  data() {
    return {
      team_requested_skills: [],
      planning_status_items: ["U", "I", "P", "F"],
      job_type_list: ["composite", "appt", "visit", "event"],
    };
  },
  mounted() {
    this.selectInventory();
    if (this.jobId != undefined) {
      this.getByJobIdNoToken({ job_id: this.jobId, token: this.token });
    }
  },
  computed: {
    ...mapFields("job", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.description",
      "selected.created_at",
      "selected.planning_status",
      "selected.tags",
      "selected.job_type",

      // K
      "selected.team",
      "selected.location",
      "selected.flex_form_data",
      "selected.requested_start_datetime",
      "selected.requested_duration_minutes",
      "selected.requested_primary_worker",
      //
      "selected.scheduled_start_datetime",
      "selected.scheduled_duration_minutes",
      "selected.scheduled_primary_worker",
      "selected.scheduled_secondary_workers",
      "selected.requested_skills",
      "selected.requested_items_conbobox",
      //
      "selected.auto_planning",
    ]),
    ...mapFields("item_inventory", ["select_inventory"]),
    select_inventory_copy: {
      get() {
        return cloneDeep(this.select_inventory);
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },
  methods: {
    ...mapMutations("job", ["SET_ITEMS"]),
    ...mapActions("job", ["getByJobIdNoToken", "updateJobByNoToken"]),
    ...mapActions("item_inventory", ["selectInventory"]),
    close: function () {
      window.opener = null;
      window.open("about:blank", "_top").close();
    },
    submitSaveLocal() {
      this.updateJobByNoToken(this.token);
      this.selectInventory();
    },
  },
  watch: {
    requested_items_conbobox(newVal, oldVal) {
      if (newVal) {
        let request_item = newVal.reduce((pre, cur, index) => {
          return [...pre, cur.text];
        }, []);
        this.SET_ITEMS(request_item);
      }
    },
    team(newVal, oldVal) {
      if (newVal) {
        this.team_requested_skills =
          newVal.flex_form_data["requested_skills"] != undefined
            ? newVal.flex_form_data["requested_skills"]
            : [];
      }
    },
  },
};
</script>
<style>
.edit_page {
  margin: 0 auto;
}
</style>