<template>
  <v-container grid-list-md>
    <v-layout wrap>
      <v-flex xs12>
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

      <v-flex xs4>
        <ValidationProvider name="Job Type" rules="required" immediate>
          <v-select
            slot-scope="{ errors, valid }"
            :error-messages="errors"
            :success="valid"
            v-model="job_type"
            label="Job Type"
            :items="job_type_list"
            hint="Please choose a Job Type."
            clearable
          />
        </ValidationProvider>
      </v-flex>
      <v-flex xs4>
        <ValidationProvider name="Job Status" rules="required" immediate>
          <v-select
            v-model="life_cycle_status"
            :items="life_cycle_status_items"
            label="Job Status"
            slot-scope="{ errors, valid }"
            :error-messages="errors"
            :success="valid"
            hint="Job Life Cycle Status"
            clearable
            required
          ></v-select>
        </ValidationProvider>
      </v-flex>
      <v-flex xs4>
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
          ></v-select>
        </ValidationProvider>
      </v-flex>

      <v-flex xs6>
        <team-select v-model="team" rules="required"></team-select>
      </v-flex>
      <v-flex xs6>
        <location-select
          v-model="location"
          label="Location"
          rules="required"
        ></location-select>
      </v-flex>
      <v-flex xs12>
        <span class="subtitle-2">Address:</span>
        {{ location && location.geo_address_text }}
      </v-flex>

      <v-flex xs12>
        <v-divider></v-divider>
        <span class="subtitle-2">Requested As:</span>
        <v-divider></v-divider>
      </v-flex>

      <v-flex xs12>
        <v-row>
          <v-col cols="6">
            <date-picker-menu v-model="requested_start_datetime"
              >Requested Start Date</date-picker-menu
            >
          </v-col>
          <v-col cols="6">
            <time-picker-menu
              v-model="requested_start_datetime"
            ></time-picker-menu>
          </v-col>
        </v-row>
      </v-flex>
      <v-flex xs6>
        <ValidationProvider
          name="Requested Primary Worker"
          rules="required"
          immediate
        >
          <worker-select
            v-model="requested_primary_worker"
            slot-scope="{ errors, valid }"
            label="Requested Primary Worker (Optional)"
            :error-messages="errors"
            :success="valid"
            hint="The job's current commander"
            clearable
            required
          ></worker-select>
        </ValidationProvider>
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

      <v-flex xs12>
        <v-divider></v-divider>
        <span class="subtitle-2">Scheduled To:</span>
        <v-divider></v-divider>
      </v-flex>

      <v-flex xs12>
        <v-row>
          <v-col cols="6">
            <date-picker-menu
              v-model="scheduled_start_datetime"
            ></date-picker-menu>
          </v-col>
          <v-col cols="6">
            <time-picker-menu
              v-model="scheduled_start_datetime"
            ></time-picker-menu>
          </v-col>
        </v-row>
      </v-flex>
      <v-flex xs6>
        <worker-select
          v-model="scheduled_primary_worker"
          label="Scheduled Primary Worker"
          hint="The job's current reporter"
          clearable
        ></worker-select>
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
        <WorkerCombo
          v-model="scheduled_secondary_workers"
          label="Scheduled Secondary Workers"
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

      <v-flex xs12>
        <v-divider></v-divider>
        <span class="subtitle-2">Other Optional Information:</span>
        <v-divider></v-divider>
      </v-flex>

      <v-flex xs12>
        <v-text-field
          v-model="name"
          label="Job Name"
          hint="Job Name"
          clearable
        />
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
        <v-textarea
          v-model="description"
          label="Description"
          hint="Description of job."
          clearable
        />
      </v-flex>
      <v-flex xs12>
        <tag-filter-combobox label="Tags" v-model="tags" />
      </v-flex>
    </v-layout>
  </v-container>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import WorkerSelect from "@/worker/WorkerSelect.vue";
import DatePickerMenu from "@/components/DatePickerMenu.vue";
import TimePickerMenu from "@/components/TimePickerMenu.vue";
import TeamSelect from "@/team/TeamSelect.vue";
import TagFilterCombobox from "@/tag/TagFilterCombobox.vue";
import WorkerCombo from "@/worker/WorkerCombobox.vue"; // ee-eslint-disable-line no-unused-vars
import LocationSelect from "@/location/LocationSelect.vue";
import InventoryCombobox from "@/item_inventory/InventoryCombobox.vue";
import { cloneDeep } from "lodash";

import { mapActions, mapMutations } from "vuex";
import { mapGetters } from "vuex";

extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "JobPlannerDetailsTab",

  components: {
    ValidationProvider,
    WorkerSelect,
    WorkerCombo,
    TeamSelect,
    TagFilterCombobox,
    TimePickerMenu,
    DatePickerMenu,
    LocationSelect,
    InventoryCombobox,
  },

  data() {
    return {
      team_requested_skills: [],
      planning_status_items: ["U", "I", "P", "F"],
      life_cycle_status_items: [
        "Created",
        "Onsite_Started",
        "Completed",
        "Customer_Approved",
        "Planner_Approved",
        "Cancelled",
      ],
      // statuses: ["Active", "Stable", "Closed"],
      // visibilities: ["Open", "Restricted"],
      job_type_list: ["composite", "appt", "visit", "event"],
    };
  },

  computed: {
    ...mapFields("job", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.description",
      "selected.created_at",
      "selected.planning_status",
      "selected.life_cycle_status",
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
    ...mapGetters("auth", ["getPermission"]),
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