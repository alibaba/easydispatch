<template>
  <v-container grid-list-md>
    <v-layout wrap>
      <v-flex xs12>
        <ValidationProvider name="location_code" rules="required" immediate>
          <v-text-field
            v-model="selected.location.location_code"
            slot-scope="{ errors, valid }"
            :error-messages="errors"
            :success="valid"
            label="location_code"
            hint="A name for your   location."
            clearable
            required
          />
        </ValidationProvider>
      </v-flex>
      <v-flex xs6>
        <ValidationProvider name="geo_longitude" rules="required" immediate>
          <v-text-field
            v-model="selected.location.geo_longitude"
            slot-scope="{ errors, valid }"
            :error-messages="errors"
            :success="valid"
            label="geo_longitude"
            hint="x, or longitude."
            clearable
            required
          />
        </ValidationProvider>
      </v-flex>
      <v-flex xs6>
        <ValidationProvider name="geo_latitude" rules="required" immediate>
          <v-text-field
            v-model="selected.location.geo_latitude"
            slot-scope="{ errors, valid }"
            :error-messages="errors"
            :success="valid"
            label="geo_latitude"
            hint="y, or geo_latitude."
            clearable
            required
          />
        </ValidationProvider>
      </v-flex>

      <v-flex xs12>
        <ValidationProvider name="selected.location.geo_address_text">
          <v-textarea
            v-model="selected.location.geo_address_text"
            slot-scope="{ errors, valid }"
            label="Description"
            :error-messages="errors"
            :success="valid"
            hint="A description for your   location."
            clearable
            required
          />
        </ValidationProvider>
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
import TagFilterCombobox from "@/tag/TagFilterCombobox.vue";

extend("required", {
  ...required,
  message: "This field is required"
});

export default {
  name: "JobLocationTab",

  components: {
    ValidationProvider,
    TagFilterCombobox
  },

  data() {
    return {
      statuses: ["Active", "Stable", "Closed"],
      visibilities: ["Open", "Restricted"]
    };
  },

  computed: {
    ...mapFields("job", ["selected"])
  }
};
</script>
