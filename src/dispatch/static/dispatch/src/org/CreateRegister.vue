<template>
  <v-dialog v-model="showCreateEdit" persistent max-width="600px">
    <ValidationObserver disabled v-slot="{ invalid, validated }">
      <v-card>
        <v-card-title>
          <span class="headline">Create Organization Invitation Code</span>
        </v-card-title>
        <v-card-text>
          <ValidationProvider name="role" rules="required" immediate>
            <v-select
              v-model="role"
              :items="role_item"
              label="User Role"
              slot-scope="{ errors, valid }"
              :error-messages="errors"
              :success="valid"
              hint="User Role"
              clearable
              required
            ></v-select>
          </ValidationProvider>
          <team-select v-model="team" rules="required"></team-select>
          <v-text-field v-model="register_code" label="Register Code" disabled />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="closeCreateEditDialog()">Cancel</v-btn>
          <v-btn
            color="info"
            text
            @click="addUserOrg({ role: role,team: team})"
            :disabled="invalid || !validated"
          >Create</v-btn>
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
import TeamSelect from "@/team/TeamSelect.vue";

extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "CreateRegister",
  data() {
    return {
      role_item: ["Worker", "Planner", "Owner"],
      role: "Worker",
      team: null,
    };
  },
  destroyed() {},
  components: {
    ValidationObserver,
    ValidationProvider,
    TeamSelect,
  },
  computed: {
    ...mapFields("org", ["dialogs.showCreateEdit", "register_code"]),
  },

  methods: {
    ...mapActions("org", ["addUserOrg", "closeCreateEditDialog", "copy_code"]),
  },
};
</script>
