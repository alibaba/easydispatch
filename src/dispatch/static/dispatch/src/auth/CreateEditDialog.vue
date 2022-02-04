<template>
  <v-dialog v-model="showCreateEdit" persistent max-width="600px">
    <ValidationObserver disabled v-slot="{ invalid, validated }">
      <v-card>
        <v-card-title>
          <span class="headline">Create a New Organization</span>
        </v-card-title>
        <v-card-text>
          Organizations represent the top level in your hierarchy. You'll be able to bundle a
          collection of user within an organization.
          <ValidationProvider name="code" rules="required" immediate>
            <v-text-field
              v-model="code"
              label="code"
              hint="A name for your saved search."
              slot-scope="{ errors, valid }"
              :error-messages="errors"
              :success="valid"
              clearable
              required
            />
          </ValidationProvider>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="showCreateEditDialog(false)">Cancel</v-btn>
          <v-btn color="info" text @click="saveOrg()" :disabled="invalid || !validated">Create</v-btn>
        </v-card-actions>
      </v-card>
    </ValidationObserver>
  </v-dialog>
</template>

<script>
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";

import { mapActions } from "vuex";
import { mapFields } from "vuex-map-fields";

extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "OrganizationCreateEditDialog",
  data() {
    return {};
  },
  components: {
    ValidationObserver,
    ValidationProvider,
  },
  computed: {
    ...mapFields("auth", ["org.code", "dialogs.showCreateEdit"]),
  },

  methods: {
    ...mapActions("auth", ["saveOrg", "showCreateEditDialog"]),
  },
};
</script>
