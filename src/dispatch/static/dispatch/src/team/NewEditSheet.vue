<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-navigation-drawer v-model="showCreateEdit" app clipped right width="500">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
            <v-list-item-title v-else class="title">New</v-list-item-title>
            <v-list-item-subtitle>Team</v-list-item-subtitle>
          </v-list-item-content>
          <v-btn
            icon
            color="primary"
            :loading="loading"
            :disabled="invalid || !validated"
            @click="save()"
          >
            <v-icon>save</v-icon>
          </v-btn>
          <v-btn icon color="secondary" @click="closeCreateEdit()">
            <v-icon>close</v-icon>
          </v-btn>
        </v-list-item>
      </template>
      <v-card flat>
        <v-card-text>
          <v-container grid-list-md>
            <v-layout wrap>
              <v-flex xs12>
                <span class="subtitle-2">Team Details</span>
              </v-flex>
              <v-flex xs12>
                <ValidationProvider name="TeamCode" rules="required" immediate>
                  <v-text-field
                    v-model="code"
                    slot-scope="{ errors, valid }"
                    label="Code"
                    :error-messages="errors"
                    :success="valid"
                    hint="The unique key for the team."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>
              <v-flex xs12>
                <ValidationProvider name="Name" rules="required" immediate>
                  <v-text-field
                    v-model="name"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Name"
                    hint="A name for your team."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>
              <v-flex xs12>
                <service-select v-model="planner_service" />
              </v-flex>
              <v-flex xs12>
                <span class="subtitle-2">Planning Window</span>
              </v-flex>

              <v-flex xs12>
                <ValidationProvider name="env_start_day" rules="required" immediate>
                  <v-text-field
                    v-model="flex_form_data.env_start_day"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Planning Start Day"
                    hint="Planning Start Day in format of YYYYMMDD"
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>

              <v-flex xs12>
                <ValidationProvider name="nbr_of_days_planning_window" rules="required" immediate>
                  <v-text-field
                    v-model="flex_form_data.nbr_of_days_planning_window"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Planning Days"
                    hint="How many days to plan e.g. 1, 2, 3, ..."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>
              <v-flex xs12>
                <v-btn
                  color="primary"
                  dark
                  class="mb-2"
                  @click="reset_planning_window()"
                >ResetPlanningWindow</v-btn>
              </v-flex>
            </v-layout>
          </v-container>
        </v-card-text>
      </v-card>
    </v-navigation-drawer>
  </ValidationObserver>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import ServiceSelect from "@/service/ServiceSelect.vue";
extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "ServiceNewEditSheet",

  components: {
    ValidationObserver,
    ValidationProvider,
    ServiceSelect,
  },

  computed: {
    ...mapFields("team", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.description",
      "selected.planner_service",
      "selected.flex_form_data",
      "selected.loading",
      "dialogs.showCreateEdit",
    ]),
  },

  methods: {
    ...mapActions("team", ["save", "closeCreateEdit", "reset_planning_window"]),
  },
};
</script>
