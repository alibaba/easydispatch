<template>
  <v-container grid-list-md>
    <v-layout wrap>
      <v-flex xs12>
        <span class="subtitle-2">Details</span>
      </v-flex>
      <v-flex xs12>
        <ValidationProvider name="Code" rules="required" immediate>
          <v-text-field
            v-model="code"
            slot-scope="{ errors, valid }"
            :error-messages="errors"
            :success="valid"
            label="Code"
            hint="Worker code as an unique key"
            clearable
            required
          />
        </ValidationProvider>
      </v-flex>
      <v-flex xs12>
        <ValidationProvider name="team" rules="required" immediate>
          <team-select
            v-model="team"
            slot-scope="{ errors, valid }"
            label="Team"
            :error-messages="errors"
            :success="valid"
            hint="The team"
            clearable
            required
          ></team-select>
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
            hint="Name of worker."
            clearable
            required
          />
        </ValidationProvider>
      </v-flex>

      <v-flex xs12>
        <location-select
          v-model="location"
          label="Location"
          hint="The home location"
          clearable
          required
        ></location-select>
      </v-flex>
    </v-layout>
  </v-container>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import TeamSelect from "@/team/TeamSelect.vue";
import LocationSelect from "@/location/LocationSelect.vue";

extend("required", {
  ...required,
  message: "This field is required"
});

export default {
  name: "WorkerNewEditSheet",

  components: {
    ValidationProvider,
    TeamSelect,
    LocationSelect
  },

  computed: {
    ...mapFields("worker", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.team",
      "selected.location",
      "selected.loading",
      "selected.flex_form_data",
      "dialogs.showCreateEdit"
    ])
  }
};
</script>
